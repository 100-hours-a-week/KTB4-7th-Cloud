# Existing production resources; adoption only.

resource "aws_db_subnet_group" "memme_db_subnet_group" {
  description = "Private RDS subnets for memme MySQL"
  name        = "memme-db-subnet-group"
  region      = "ap-northeast-2"
  subnet_ids  = [aws_subnet.subnet_04319b3c278097d7a.id, aws_subnet.subnet_0f80faec15de9dffc.id]
  tags        = {}

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_db_instance" "memme_mysql" {
  allocated_storage = 20


  auto_minor_version_upgrade = true
  availability_zone          = "ap-northeast-2c"
  backup_retention_period    = 7
  backup_target              = "region"
  backup_window              = "13:10-13:40"
  ca_cert_identifier         = "rds-ca-rsa2048-g1"
  copy_tags_to_snapshot      = true

  customer_owned_ip_enabled = false
  database_insights_mode    = "standard"
  db_name                   = "memme"
  db_subnet_group_name      = aws_db_subnet_group.memme_db_subnet_group.name
  dedicated_log_volume      = false
  delete_automated_backups  = true
  deletion_protection       = true



  enabled_cloudwatch_logs_exports = []
  engine                          = "mysql"
  engine_lifecycle_support        = "open-source-rds-extended-support-disabled"
  engine_version                  = "8.4.9"

  iam_database_authentication_enabled = false
  identifier                          = "memme-mysql"
  instance_class                      = "db.t4g.micro"
  iops                                = 3000
  kms_key_id                          = "arn:aws:kms:ap-northeast-2:613538400341:key/688da05e-cd0f-4d32-8e09-86cbe728bf07"
  license_model                       = "general-public-license"
  maintenance_window                  = "sun:14:57-sun:15:27"

  max_allocated_storage = 1000
  monitoring_interval   = 0
  multi_az              = false
  network_type          = "IPV4"
  option_group_name     = "default:mysql-8-4"
  parameter_group_name  = "default.mysql8.4"



  performance_insights_enabled          = false
  performance_insights_retention_period = 0
  port                                  = 3306
  publicly_accessible                   = false
  region                                = "ap-northeast-2"

  skip_final_snapshot = true

  storage_encrypted  = true
  storage_throughput = 125
  storage_type       = "gp3"
  tags               = {}


  username               = "memmeadmin"
  vpc_security_group_ids = [aws_security_group.memme_db_sg.id]

  lifecycle {
    prevent_destroy = true
  }
}
