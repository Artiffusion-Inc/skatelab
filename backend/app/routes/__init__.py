"""Route module exports — each submodule provides a Litestar Router."""

from __future__ import annotations

from litestar import Router

from app.routes.auth import AuthController
from app.routes.choreography import ChoreographyController
from app.routes.comments import CommentsController
from app.routes.connections import ConnectionsController
from app.routes.detect import DetectController
from app.routes.gamification import GamificationController
from app.routes.metrics import MetricsController
from app.routes.metrics_summary import ElementSummaryController
from app.routes.misc import MiscController
from app.routes.models import ModelsController
from app.routes.notifications import NotificationsController
from app.routes.phases import PhasesController
from app.routes.process import ProcessController
from app.routes.scores import ScoresController
from app.routes.sessions import SessionsController
from app.routes.training_plans import TrainingPlansController
from app.routes.uploads import UploadsController
from app.routes.users import UsersController
from app.routes.workspaces import WorkspacesController

auth = Router(path="/auth", route_handlers=[AuthController])
choreography = Router(path="/choreography", route_handlers=[ChoreographyController])
connections = Router(path="/connections", route_handlers=[ConnectionsController])
detect = Router(path="/detect", route_handlers=[DetectController])
metrics = Router(path="/metrics", route_handlers=[MetricsController, ElementSummaryController])
misc = Router(path="", route_handlers=[MiscController])
models = Router(path="/models", route_handlers=[ModelsController])
notifications = Router(path="/notifications", route_handlers=[NotificationsController])
process = Router(path="/process", route_handlers=[ProcessController])
sessions = Router(
    path="/sessions",
    route_handlers=[SessionsController, ScoresController, PhasesController, CommentsController],
)
training_plans = Router(path="/training-plans", route_handlers=[TrainingPlansController])
uploads = Router(path="/uploads", route_handlers=[UploadsController])
users = Router(path="/users", route_handlers=[UsersController, GamificationController])
workspaces = Router(path="/workspaces", route_handlers=[WorkspacesController])
