# Existing production resources; adoption only.

resource "aws_secretsmanager_secret" "_memme_prod_backend_runtime" {
  description = "Memme backend production runtime configuration"


  name = "/memme/prod/backend/runtime"

  region = "ap-northeast-2"
  tags   = {}


  lifecycle {
    prevent_destroy = true
    # Delete/replica request options are not returned by DescribeSecret.
    ignore_changes = [recovery_window_in_days, force_overwrite_replica_secret]
  }
}

resource "aws_secretsmanager_secret" "_memme_prod_ai_runtime" {
  description = "Memme AI production runtime configuration"


  name = "/memme/prod/ai/runtime"

  region = "ap-northeast-2"
  tags   = {}


  lifecycle {
    prevent_destroy = true
    # Delete/replica request options are not returned by DescribeSecret.
    ignore_changes = [recovery_window_in_days, force_overwrite_replica_secret]
  }
}
