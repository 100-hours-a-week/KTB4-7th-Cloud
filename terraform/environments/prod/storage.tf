# Existing production resources; adoption only.

resource "aws_s3_bucket_server_side_encryption_configuration" "memme_sales_uploads_613538400341" {
  bucket = aws_s3_bucket.uploads.id
  region = "ap-northeast-2"
  rule {
    blocked_encryption_types = ["SSE-C"]
    bucket_key_enabled       = true
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_ownership_controls" "memme_sales_uploads_613538400341" {
  bucket = aws_s3_bucket.uploads.id
  region = "ap-northeast-2"
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket" "uploads" {
  bucket              = "memme-sales-uploads-613538400341"
  bucket_namespace    = "global"
  force_destroy       = false
  object_lock_enabled = false
  region              = "ap-northeast-2"
  tags                = {}

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "memme_sales_uploads_613538400341" {
  bucket                                 = aws_s3_bucket.uploads.id
  region                                 = "ap-northeast-2"
  transition_default_minimum_object_size = "all_storage_classes_128K"
  rule {
    id     = "expire-noncurrent-versions-30d"
    status = "Enabled"
    noncurrent_version_expiration {

      noncurrent_days = 30
    }
  }
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_public_access_block" "memme_sales_uploads_613538400341" {
  block_public_acls       = true
  block_public_policy     = true
  bucket                  = aws_s3_bucket.uploads.id
  ignore_public_acls      = true
  region                  = "ap-northeast-2"
  restrict_public_buckets = true

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "memme_sales_uploads_613538400341" {
  bucket = aws_s3_bucket.uploads.id

  region = "ap-northeast-2"
  versioning_configuration {
    mfa_delete = "Disabled"
    status     = "Enabled"
  }
  lifecycle {
    prevent_destroy = true
  }
}
