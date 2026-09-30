-- Add a default weight to existing preference rows without discarding data.
ALTER TABLE employee_preferences ADD COLUMN weight FLOAT DEFAULT 1.0;
