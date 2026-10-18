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

# Retired original RDS: never recreate or destroy through a future apply.
removed {
  from = aws_db_instance.memme_mysql
  lifecycle {
    destroy = false
  }
}
