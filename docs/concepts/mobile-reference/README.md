# SkateLab Mobile Reference Screens

Reference screenshots received on 2026-08-29. All images use portrait canvas `853x1844`.

These are product/design references, not proof of current implementation. Keep them separate from production UI assets. Original files remain in `/home/michael/Downloads/`.

## Screen Index

| File | Screen | Notes |
| --- | --- | --- |
| `01-auth-register.png` | Registration | Email/password and social sign-in entry. |
| `02-analysis-filters.png` | Analysis filters | Element, attempts, status, period, season filters. |
| `03-auth-logout-confirmation.png` | Logout confirmation | Destructive confirmation dialog. |
| `04-program-add-element.png` | Add program element | Element catalog with attempts and status. |
| `05-training-complete.png` | Training complete | Summary metrics and saved training action. |
| `06-program-create-details.png` | New program details | Program name, season, type, athlete, duration. |
| `07-program-music-choreography.png` | Music and choreography | Music upload, rink diagram, selected elements. |
| `08-program-created.png` | Program created | Success confirmation and open-program action. |
| `09-program-report-pdf-ready.png` | PDF report ready | Export success dialog. |
| `10-auth-forgot-password.png` | Forgot password | Email recovery request. |
| `11-auth-new-password.png` | New password | Password reset form and rules. |
| `12-auth-verify-email.png` | Verify email | Email verification and resend action. |
| `13-analysis-camera-permission.png` | Camera permission | Analysis entry with system camera permission dialog. |
| `14-analysis-list.png` | Analysis list | Recent analyses and bottom navigation. |
| `15-analysis-empty.png` | Empty analysis state | No analyses yet; first-video CTA. |
| `16-analysis-processing-error.png` | Analysis processing error | Failed analysis with retry/settings/cancel actions. |
| `17-notifications.png` | Notifications | Analysis, coach comment, training, export events. |
| `18-auth-register-variant-2.png` | Registration variant | Duplicate reference from second capture batch. |
| `19-analysis-filters-variant-2.png` | Analysis filters variant | Duplicate reference from second capture batch. |
| `20-auth-logout-confirmation-variant-2.png` | Logout confirmation variant | Duplicate reference from second capture batch. |
| `21-auth-forgot-password-variant-2.png` | Forgot password variant | Duplicate reference from second capture batch. |
| `22-auth-new-password-variant-2.png` | New password variant | Duplicate reference from second capture batch. |
| `23-auth-verify-email-variant-2.png` | Verify email variant | Duplicate reference from second capture batch. |
| `24-analysis-camera-permission-variant-2.png` | Camera permission variant | Duplicate reference from second capture batch. |
| `25-analysis-list-variant-2.png` | Analysis list variant | Duplicate reference from second capture batch. |
| `26-analysis-empty-variant-2.png` | Empty analysis state variant | Duplicate reference from second capture batch. |
| `27-analysis-processing-error-variant-2.png` | Processing error variant | Duplicate reference from second capture batch. |
| `28-notifications-variant-2.png` | Notifications variant | Duplicate reference from second capture batch. |

## Visual Direction

- Light lavender-white background with purple primary actions.
- Rounded cards, sheets, fields, and dialogs.
- Bottom navigation with five product areas.
- Russian-first copy and compact mobile information density.
- Analysis is the primary home surface; programs and notifications are secondary product areas.
- Use real text and accessible controls in implementation; screenshots are visual references only.

## Reproduction Scope

The full application should reproduce these flows:

1. Auth and account recovery.
2. Analysis creation from camera or gallery.
3. Camera/BLE preparation and multimodal capture.
4. Upload, processing, failure, retry, and recovery.
5. Completed analysis with evidence, diagnostics, and recommendation.
6. Program creation, music, choreography, and PDF export.
7. Notifications linked to actionable destinations.

## Important Product Boundary

Reference screens show broad product surface. Current validated implementation is narrower: synthetic multimodal Axel analysis. Build remaining screens around existing API contracts and mark sensor-fusion output `synthetic/unvalidated` until WT901 hardware validation is complete.
