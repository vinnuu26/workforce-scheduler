-- Add persisted employee skill proficiency; legacy associations default to level 1.
ALTER TABLE employee_skills ADD COLUMN proficiency INTEGER NOT NULL DEFAULT 1;
