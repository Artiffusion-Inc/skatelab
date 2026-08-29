"""Choreography planner API routes."""

from __future__ import annotations

import asyncio
import tempfile
from collections.abc import Sequence  # noqa: TC003
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from litestar import Controller, Response, delete, get, post, put
from litestar.connection import Request  # noqa: TC002
from litestar.datastructures import UploadFile  # noqa: TC002
from litestar.exceptions import ClientException
from litestar.params import Parameter
from litestar.status_codes import (
    HTTP_201_CREATED,
    HTTP_204_NO_CONTENT,
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
    HTTP_422_UNPROCESSABLE_ENTITY,
)

from app.auth.deps import CurrentUser, DbDep, VerifiedUser
from app.crud.choreography import (
    count_programs_by_user,
    create_music_analysis,
    create_program,
    delete_program,
    find_music_by_fingerprint,
    get_music_analysis_by_id,
    get_program_by_id,
    list_programs_by_user,
    update_music_analysis,
    update_program,
)
from app.schemas import (
    ChoreographyProgramResponse,
    ElementDefResponse,
    ElementRegistryResponse,
    ExportRequest,
    GenerateRequest,
    GenerateResponse,
    Layout,
    LayoutElement,
    ProgramListResponse,
    RenderRinkRequest,
    SaveProgramRequest,
    UploadMusicResponse,
    ValidateRequest,
    ValidateResponse,
)
from app.services.choreography.csp_solver import solve_layout
from app.services.choreography.music_analyzer import extract_features_for_csp
from app.services.choreography.rink_renderer import render_rink
from app.services.choreography.rules_engine import validate_layout as validate_layout_engine
from app.services.notification_events import export_ready
from app.services.pdf_report import generate_program_pdf
from app.storage import upload_file

if TYPE_CHECKING:
    from app.models.choreography import ChoreographyProgram

MAX_MUSIC_UPLOAD_BYTES = 100 * 1024 * 1024  # #704: 100 MB limit


def _program_to_response(program: ChoreographyProgram) -> ChoreographyProgramResponse:
    """Convert ORM ChoreographyProgram to response schema."""
    return ChoreographyProgramResponse.model_validate(program)


async def _verify_music_ownership(db: DbDep, music_id: str | None, user_id: str) -> None:
    """#707 #708: Check that music_analysis_id belongs to the user, if provided."""
    if music_id is None:
        return
    music = await get_music_analysis_by_id(db, music_id)
    if not music:
        raise ClientException(
            status_code=HTTP_404_NOT_FOUND,
            detail="Music analysis not found",
        )
    if music.user_id != user_id:
        raise ClientException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Not authorized",
        )


class ChoreographyController(Controller):
    path = ""
    tags: ClassVar[Sequence[str]] = ["choreography"]

    # -----------------------------------------------------------------------
    # Music upload & analysis
    # -----------------------------------------------------------------------

    @post("/music/upload", status_code=HTTP_201_CREATED)
    async def upload_music(
        self,
        request: Request,
        verified_user: VerifiedUser,
        db: DbDep,
        file: UploadFile,
    ) -> UploadMusicResponse:
        """Upload an audio file and enqueue analysis job.

        Deduplicates by SHA256 fingerprint — returns cached result if
        the same file was already analyzed (by any user).
        """
        import asyncio
        import hashlib
        import logging

        logger = logging.getLogger(__name__)

        suffix = (
            f".{file.filename.rsplit('.', 1)[-1]}"
            if file.filename and "." in file.filename
            else ".mp3"
        )
        content = await file.read()
        if len(content) > MAX_MUSIC_UPLOAD_BYTES:  # #704: file size limit
            raise ClientException(
                status_code=HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"File too large (max {MAX_MUSIC_UPLOAD_BYTES // (1024 * 1024)} MB)",
            )

        # Dedup: check if this exact file was already analyzed
        fingerprint = hashlib.sha256(content).hexdigest()
        existing = await find_music_by_fingerprint(
            db, fingerprint, user_id=verified_user.id
        )  # #705: scope to own music
        if existing:
            logger.info("Music fingerprint hit: %s (existing=%s)", fingerprint, existing.id)
            return UploadMusicResponse(music_id=existing.id, filename=existing.filename)

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        # Create record as "pending"
        music = await create_music_analysis(
            db,
            user_id=verified_user.id,
            filename=file.filename or "unknown",
            audio_url="",
            duration_sec=0,
            status="pending",
            fingerprint=fingerprint,
        )

        try:
            # Upload to S3 (blocking boto3 — run in thread pool)
            s3_key = f"music/{verified_user.id}/{music.id}{suffix}"
            logger.info("Uploading to S3: %s", s3_key)
            await asyncio.to_thread(upload_file, tmp_path, s3_key)
            logger.info("S3 upload complete")

            # Enqueue analysis job
            await request.app.state.arq_pool.enqueue_job(
                "analyze_music_task",
                music_id=music.id,
                s3_key=s3_key,
                _queue_name="skatelab:queue:fast",
            )
            logger.info("Enqueued analyze_music_task for music_id=%s", music.id)
        except Exception as e:  # #706: broadened from (OSError, ValueError, RuntimeError) to catch FailedEnqueueError etc
            # Log the raw exception server-side (logger.exception dumps the traceback
            # with full detail); send the client only a generic user-facing message
            # so internal S3 infrastructure (bucket name, endpoint host, paths) does
            # not leak through the error detail. See issue #343.
            logger.exception("Failed to upload or enqueue music analysis")
            await update_music_analysis(db, music, status="failed")
            raise ClientException(
                status_code=HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Upload failed, please try again",
            ) from e
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        return UploadMusicResponse(music_id=music.id, filename=music.filename)

    @get("/music/{music_id:str}/analysis")
    async def get_music_analysis(self, music_id: str, user: CurrentUser, db: DbDep) -> dict:
        """Get music analysis result."""
        music = await get_music_analysis_by_id(db, music_id)
        if not music:
            raise ClientException(
                status_code=HTTP_404_NOT_FOUND,
                detail="Music analysis not found",
            )
        if music.user_id != user.id:
            raise ClientException(
                status_code=HTTP_403_FORBIDDEN,
                detail="Not authorized",
            )
        return {
            "id": music.id,
            "user_id": music.user_id,
            "filename": music.filename,
            "audio_url": music.audio_url,
            "duration_sec": music.duration_sec,
            "bpm": music.bpm,
            "meter": music.meter,
            "structure": music.structure,
            "energy_curve": music.energy_curve,
            "downbeats": music.downbeats,
            "peaks": music.peaks,
            "status": music.status,
            "created_at": music.created_at.isoformat() if music.created_at else None,
            "updated_at": music.updated_at.isoformat() if music.updated_at else None,
        }

    # -----------------------------------------------------------------------
    # Layout generation & validation
    # -----------------------------------------------------------------------

    @post("/generate")
    async def generate_layout(
        self, data: GenerateRequest, verified_user: VerifiedUser, db: DbDep
    ) -> GenerateResponse:
        """Generate choreography layouts via CSP solver."""
        music = await get_music_analysis_by_id(db, data.music_id)
        if not music:
            raise ClientException(
                status_code=HTTP_404_NOT_FOUND,
                detail="Music analysis not found",
            )
        if music.user_id != verified_user.id:
            raise ClientException(
                status_code=HTTP_403_FORBIDDEN,
                detail="Not authorized",
            )

        analysis = {
            "duration_sec": music.duration_sec,
            "peaks": music.peaks or [],
            "structure": music.structure or [],
        }
        music_features = extract_features_for_csp(analysis)
        layouts = await asyncio.to_thread(
            solve_layout,
            inventory=data.inventory,
            music_features=music_features,
            discipline=data.discipline,
            segment=data.segment,
        )

        response_layouts = []
        for layout in layouts:
            elements = [
                LayoutElement(
                    code=e["code"],
                    goe=e.get("goe", 0),
                    timestamp=e.get("timestamp", 0.0),
                    position=e.get("position"),
                    is_back_half=e.get("is_back_half", False),  # #716: was hardcoded False
                    is_jump_pass="jump_pass_index" in e,
                    jump_pass_index=e.get("jump_pass_index"),
                )
                for e in layout["elements"]
            ]
            response_layouts.append(
                Layout(
                    elements=elements,
                    total_tes=layout["total_tes"],
                    back_half_indices=layout["back_half_indices"],
                )
            )
        return GenerateResponse(layouts=response_layouts)

    @post("/validate")
    async def validate_choreography(
        self, data: ValidateRequest, verified_user: VerifiedUser
    ) -> ValidateResponse:  # #712: added auth
        """Validate a layout against ISU rules."""
        layout = {
            "discipline": data.discipline,
            "segment": data.segment,
            "elements": data.elements,
        }
        result = validate_layout_engine(layout)
        return ValidateResponse(
            is_valid=result.is_valid,
            errors=result.errors,
            warnings=result.warnings,
        )

    # -----------------------------------------------------------------------
    # Rink rendering
    # -----------------------------------------------------------------------

    @post("/render-rink")
    async def render_rink_diagram(
        self, data: RenderRinkRequest, verified_user: VerifiedUser
    ) -> dict:  # #709: added auth
        """Render an SVG rink diagram with element markers."""
        svg = render_rink(
            data.elements,
            width=data.width,
            height=data.height,
            rink_width=data.rink_width,
            rink_height=data.rink_height,
        )
        return {"svg": svg}

    # -----------------------------------------------------------------------
    # Element registry
    # -----------------------------------------------------------------------

    @get("/elements/registry")
    async def get_elements_registry(
        self, verified_user: VerifiedUser
    ) -> ElementRegistryResponse:  # #711: added auth
        from app.services.choreography.elements_db import ELEMENTS

        elements = [
            ElementDefResponse(
                code=el.code,
                name=el.name,
                type=el.type.value,
                base_value=el.base_value,
                rotations=el.rotations,
                has_toe_pick=el.has_toe_pick,
                entry_edge=el.entry_edge,
                exit_edge=el.exit_edge,
                combo_eligible=el.combo_eligible,
                short_program_eligible=el.short_program_eligible,
            )
            for el in ELEMENTS.values()
        ]
        return ElementRegistryResponse(elements=elements, season="2025_26")

    # -----------------------------------------------------------------------
    # Program CRUD
    # -----------------------------------------------------------------------

    @get("/programs")
    async def list_programs(
        self,
        user: CurrentUser,
        db: DbDep,
        limit: int = Parameter(default=20, ge=1, le=100),
        offset: int = Parameter(default=0, ge=0),
    ) -> ProgramListResponse:
        """List user's choreography programs."""
        programs = await list_programs_by_user(db, user.id, limit=limit, offset=offset)
        total = await count_programs_by_user(db, user.id)
        page = (offset // limit) + 1 if limit else 1  # type: ignore[operator]
        pages = (total + limit - 1) // limit if limit else 1  # type: ignore[operator]

        return ProgramListResponse(
            programs=[_program_to_response(p) for p in programs],
            total=total,
            page=page,
            page_size=limit,  # type: ignore[arg-type]
            pages=pages,
        )

    @post("/programs", status_code=HTTP_201_CREATED)
    async def create_new_program(
        self, data: SaveProgramRequest, verified_user: VerifiedUser, db: DbDep
    ) -> ChoreographyProgramResponse:
        """Create a new choreography program."""
        await _verify_music_ownership(db, data.music_analysis_id, verified_user.id)  # #707
        program = await create_program(
            db,
            user_id=verified_user.id,
            discipline=data.discipline or "mens_singles",
            segment=data.segment or "free_skate",
            music_analysis_id=data.music_analysis_id,
            title=data.title,
            layout=data.layout,
            total_tes=data.total_tes,
            estimated_goe=data.estimated_goe,
            estimated_pcs=data.estimated_pcs,
            estimated_total=data.estimated_total,
            is_valid=data.is_valid,
            validation_errors=data.validation_errors,
            validation_warnings=data.validation_warnings,
        )
        return _program_to_response(program)

    @get("/programs/{program_id:str}")
    async def get_program(
        self, program_id: str, user: CurrentUser, db: DbDep
    ) -> ChoreographyProgramResponse:
        """Get a choreography program."""
        program = await get_program_by_id(db, program_id)
        if not program:
            raise ClientException(
                status_code=HTTP_404_NOT_FOUND,
                detail="Program not found",
            )
        if program.user_id != user.id:
            raise ClientException(
                status_code=HTTP_403_FORBIDDEN,
                detail="Not authorized",
            )
        return _program_to_response(program)

    @put("/programs/{program_id:str}")
    async def update_existing_program(
        self,
        program_id: str,
        data: SaveProgramRequest,
        verified_user: VerifiedUser,
        db: DbDep,
    ) -> ChoreographyProgramResponse:
        """Update a choreography program."""
        program = await get_program_by_id(db, program_id)
        if not program:
            raise ClientException(
                status_code=HTTP_404_NOT_FOUND,
                detail="Program not found",
            )
        if program.user_id != verified_user.id:
            raise ClientException(
                status_code=HTTP_403_FORBIDDEN,
                detail="Not authorized",
            )
        await _verify_music_ownership(db, data.music_analysis_id, verified_user.id)  # #708
        program = await update_program(
            db,
            program,
            discipline=data.discipline,  # #713: was silently dropped
            segment=data.segment,  # #713: was silently dropped
            title=data.title,
            music_analysis_id=data.music_analysis_id,
            layout=data.layout,
            total_tes=data.total_tes,
            estimated_goe=data.estimated_goe,
            estimated_pcs=data.estimated_pcs,
            estimated_total=data.estimated_total,
            is_valid=data.is_valid,
            validation_errors=data.validation_errors,
            validation_warnings=data.validation_warnings,
        )
        return _program_to_response(program)

    @delete("/programs/{program_id:str}", status_code=HTTP_204_NO_CONTENT)
    async def delete_existing_program(
        self, program_id: str, verified_user: VerifiedUser, db: DbDep
    ) -> None:
        """Delete a choreography program."""
        program = await get_program_by_id(db, program_id)
        if not program:
            raise ClientException(
                status_code=HTTP_404_NOT_FOUND,
                detail="Program not found",
            )
        if program.user_id != verified_user.id:
            raise ClientException(
                status_code=HTTP_403_FORBIDDEN,
                detail="Not authorized",
            )
        await delete_program(db, program)

    # -----------------------------------------------------------------------
    # Export
    # -----------------------------------------------------------------------

    @post("/programs/{program_id:str}/export")
    async def export_program(
        self,
        program_id: str,
        data: ExportRequest,
        verified_user: VerifiedUser,
        db: DbDep,
    ) -> Response[bytes] | dict[str, object]:
        """Export a program as a PDF, SVG, or JSON document."""
        program = await get_program_by_id(db, program_id)
        if not program:
            raise ClientException(
                status_code=HTTP_404_NOT_FOUND,
                detail="Program not found",
            )
        if program.user_id != verified_user.id:
            raise ClientException(
                status_code=HTTP_403_FORBIDDEN,
                detail="Not authorized",
            )

        if data.format == "pdf":
            elements = program.layout.get("elements", []) if program.layout else []
            pdf = generate_program_pdf(
                {
                    "title": program.title,
                    "discipline": program.discipline,
                    "segment": program.segment,
                    "season": program.season,
                    "elements": elements,
                    "estimated_total": program.estimated_total,
                }
            )
            await export_ready(db, user_id=verified_user.id, export_id=program_id)
            return Response(
                content=pdf,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f'attachment; filename="program-{program_id}.pdf"',
                },
            )

        if data.format == "json":
            return {
                "format": "json",
                "data": {
                    "id": program.id,
                    "title": program.title,
                    "discipline": program.discipline,
                    "segment": program.segment,
                    "season": program.season,
                    "music_analysis_id": program.music_analysis_id,
                    "layout": program.layout,
                    "total_tes": program.total_tes,
                    "estimated_goe": program.estimated_goe,
                    "estimated_pcs": program.estimated_pcs,
                    "estimated_total": program.estimated_total,
                    "is_valid": program.is_valid,
                    "validation_errors": program.validation_errors,
                    "validation_warnings": program.validation_warnings,
                },
            }

        elements = program.layout.get("elements", []) if program.layout else []
        svg = render_rink(elements)

        return {"format": "svg", "svg": svg}
