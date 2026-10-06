terraform {
  backend "s3" {
    bucket              = "memme-terraform-state-613538400341-ap-northeast-2"
    key                 = "memme/bootstrap/terraform.tfstate"
    region              = "ap-northeast-2"
    encrypt             = true
    use_lockfile        = true
    allowed_account_ids = ["613538400341"]
  }
}
