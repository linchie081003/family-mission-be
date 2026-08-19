"""
MVC Architecture (Family Mission API)
=====================================

Trace flow:  HTTP Request
           → Controller  (app/controllers/*_controller.py)
           → Service     (app/services/*_service.py)
           → Repository  (app/repositories/*_repository.py)
           → Model       (app/models/models.py)
           → View/DTO    (app/schemas.py)

Cross-cutting:
  app/core/       — config, database, auth, security helpers
  app/middleware/ — OWASP security headers, rate limiting

Legacy routers in app/routers/ re-export controllers for backward compatibility.
"""
