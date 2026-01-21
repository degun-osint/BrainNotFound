-- ============================================
-- Script de migration vers multi-tenant
-- À exécuter APRÈS import du database.sql
-- ============================================

-- Désactiver les checks FK temporairement
SET FOREIGN_KEY_CHECKS = 0;

-- ============================================
-- 1. Créer la table tenants
-- ============================================
CREATE TABLE IF NOT EXISTS `tenants` (
  `id` int NOT NULL AUTO_INCREMENT,
  `slug` varchar(50) NOT NULL,
  `name` varchar(200) NOT NULL,
  `description` text,
  `is_active` tinyint(1) DEFAULT '1',
  `max_users` int DEFAULT '0',
  `max_quizzes` int DEFAULT '0',
  `max_groups` int DEFAULT '0',
  `max_storage_mb` int DEFAULT '0',
  `contact_email` varchar(200) DEFAULT NULL,
  `contact_name` varchar(200) DEFAULT NULL,
  `internal_notes` text,
  `created_at` datetime DEFAULT NULL,
  `updated_at` datetime DEFAULT NULL,
  `monthly_ai_corrections` int DEFAULT '0',
  `monthly_quiz_generations` int DEFAULT '0',
  `monthly_class_analyses` int DEFAULT '0',
  `used_ai_corrections` int DEFAULT '0',
  `used_quiz_generations` int DEFAULT '0',
  `used_class_analyses` int DEFAULT '0',
  `usage_reset_date` date DEFAULT NULL,
  `subscription_expires_at` date DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_tenants_slug` (`slug`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ============================================
-- 2. Créer la table tenant_admins
-- ============================================
CREATE TABLE IF NOT EXISTS `tenant_admins` (
  `tenant_id` int NOT NULL,
  `user_id` int NOT NULL,
  `created_at` datetime DEFAULT NULL,
  PRIMARY KEY (`tenant_id`, `user_id`),
  KEY `user_id` (`user_id`),
  CONSTRAINT `tenant_admins_ibfk_1` FOREIGN KEY (`tenant_id`) REFERENCES `tenants` (`id`),
  CONSTRAINT `tenant_admins_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ============================================
-- 3. Ajouter tenant_id aux tables groups et quizzes
-- ============================================
-- Vérifier si la colonne existe déjà avant de l'ajouter
SET @col_exists_groups = (
  SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'groups' AND COLUMN_NAME = 'tenant_id'
);

SET @col_exists_quizzes = (
  SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'quizzes' AND COLUMN_NAME = 'tenant_id'
);

-- Ajouter colonne tenant_id à groups si elle n'existe pas
SET @sql_groups = IF(@col_exists_groups = 0,
  'ALTER TABLE `groups` ADD COLUMN `tenant_id` int DEFAULT NULL, ADD INDEX `ix_groups_tenant_id` (`tenant_id`), ADD CONSTRAINT `fk_groups_tenant_id` FOREIGN KEY (`tenant_id`) REFERENCES `tenants` (`id`)',
  'SELECT "Column tenant_id already exists in groups"'
);
PREPARE stmt FROM @sql_groups;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Ajouter colonne tenant_id à quizzes si elle n'existe pas
SET @sql_quizzes = IF(@col_exists_quizzes = 0,
  'ALTER TABLE `quizzes` ADD COLUMN `tenant_id` int DEFAULT NULL, ADD INDEX `ix_quizzes_tenant_id` (`tenant_id`), ADD CONSTRAINT `fk_quizzes_tenant_id` FOREIGN KEY (`tenant_id`) REFERENCES `tenants` (`id`)',
  'SELECT "Column tenant_id already exists in quizzes"'
);
PREPARE stmt FROM @sql_quizzes;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ============================================
-- 4. Créer le tenant par défaut et migrer les données
-- ============================================
-- Insérer tenant par défaut s'il n'existe pas
INSERT INTO `tenants` (`slug`, `name`, `description`, `is_active`, `max_users`, `max_quizzes`, `max_groups`, `max_storage_mb`, `created_at`, `updated_at`)
SELECT 'default', 'Organisation principale', 'Organisation créée automatiquement lors de la migration', 1, 0, 0, 0, 0, NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM `tenants` WHERE `slug` = 'default');

-- Récupérer l'ID du tenant default
SET @default_tenant_id = (SELECT `id` FROM `tenants` WHERE `slug` = 'default' LIMIT 1);

-- Associer tous les groupes orphelins au tenant par défaut
UPDATE `groups` SET `tenant_id` = @default_tenant_id WHERE `tenant_id` IS NULL;

-- Associer tous les quizzes orphelins au tenant par défaut
UPDATE `quizzes` SET `tenant_id` = @default_tenant_id WHERE `tenant_id` IS NULL;

-- ============================================
-- 5. Ajouter le premier admin comme admin du tenant
-- ============================================
INSERT INTO `tenant_admins` (`tenant_id`, `user_id`, `created_at`)
SELECT @default_tenant_id, `id`, NOW()
FROM `users`
WHERE `is_admin` = 1 OR `is_superadmin` = 1
AND NOT EXISTS (
  SELECT 1 FROM `tenant_admins`
  WHERE `tenant_id` = @default_tenant_id AND `user_id` = `users`.`id`
)
LIMIT 1;

-- ============================================
-- 6. Mettre à jour la version alembic
-- ============================================
DELETE FROM `alembic_version`;
INSERT INTO `alembic_version` (`version_num`) VALUES ('008_tenant_limits');

-- Réactiver les checks FK
SET FOREIGN_KEY_CHECKS = 1;

-- ============================================
-- Vérification
-- ============================================
SELECT 'Migration terminée !' AS status;
SELECT CONCAT('Tenant par défaut créé avec ID: ', @default_tenant_id) AS tenant_info;
SELECT CONCAT('Groupes migrés: ', COUNT(*)) AS groups_migrated FROM `groups` WHERE `tenant_id` = @default_tenant_id;
SELECT CONCAT('Quizzes migrés: ', COUNT(*)) AS quizzes_migrated FROM `quizzes` WHERE `tenant_id` = @default_tenant_id;
