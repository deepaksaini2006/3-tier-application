-- Run once as a MySQL admin user:   mysql -u root -p < database/schema.sql
CREATE DATABASE IF NOT EXISTS sobhasaria_admissions
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Dedicated app user (change the password!)
CREATE USER IF NOT EXISTS 'admission_app'@'localhost' IDENTIFIED BY 'ChangeMe_Strong_Pass1';
GRANT SELECT, INSERT, CREATE ON sobhasaria_admissions.* TO 'admission_app'@'localhost';
FLUSH PRIVILEGES;
