-- Persist generation filters so reviewed reschedule candidates use the same source scope.
ALTER TABLE schedules ADD COLUMN scope_department_id INTEGER;
ALTER TABLE schedules ADD COLUMN scope_project_id INTEGER;
