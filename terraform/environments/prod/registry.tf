# Existing production resources; adoption only.

resource "aws_ecr_repository" "memme_backend" {

  image_tag_mutability = "IMMUTABLE"
  name                 = "memme/backend"
  region               = "ap-northeast-2"
  tags                 = {}

  encryption_configuration {
    encryption_type = "AES256"
  }
  image_scanning_configuration {
    scan_on_push = false
  }
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_ecr_repository" "memme_ai" {

  image_tag_mutability = "IMMUTABLE"
  name                 = "memme/ai"
  region               = "ap-northeast-2"
  tags                 = {}

  encryption_configuration {
    encryption_type = "AES256"
  }
  image_scanning_configuration {
    scan_on_push = false
  }
  lifecycle {
    prevent_destroy = true
  }
}
