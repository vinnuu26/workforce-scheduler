-- Add project deadlines, shift associations, and explicit requirement hours.
-- Existing projects, shifts, and requirements remain intact; legacy shifts have no project.
ALTER TABLE projects ADD COLUMN deadline DATE;
ALTER TABLE shifts ADD COLUMN project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL;
CREATE INDEX ix_shifts_project_id ON shifts(project_id);
ALTER TABLE project_requirements ADD COLUMN required_hours FLOAT NOT NULL DEFAULT 0;
ALTER TABLE project_requirements ADD COLUMN minimum_proficiency INTEGER NOT NULL DEFAULT 1;
