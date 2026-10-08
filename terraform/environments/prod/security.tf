# Existing production resources; ECS access uses the external task SG.

resource "aws_security_group" "memme_db_sg" {
  description = "memme-db-sg"
  egress = [{
    cidr_blocks      = ["0.0.0.0/0"]
    description      = ""
    from_port        = 0
    ipv6_cidr_blocks = []
    prefix_list_ids  = []
    protocol         = "-1"
    security_groups  = []
    self             = false
    to_port          = 0
  }]
  ingress = [{
    cidr_blocks      = []
    description      = "AI to MySQL"
    from_port        = 3306
    ipv6_cidr_blocks = []
    prefix_list_ids  = []
    protocol         = "tcp"
    security_groups  = ["sg-02edb6749fab0e3f7"]
    self             = false
    to_port          = 3306
    }, {
    cidr_blocks      = []
    description      = "Backend to MySQL"
    from_port        = 3306
    ipv6_cidr_blocks = []
    prefix_list_ids  = []
    protocol         = "tcp"
    security_groups  = ["sg-0d99aedfebba0f029"]
    self             = false
    to_port          = 3306
    }, {
    cidr_blocks      = []
    description      = ""
    from_port        = 3306
    ipv6_cidr_blocks = []
    prefix_list_ids  = []
    protocol         = "tcp"
    security_groups  = ["sg-010fbd5aa0b0c5651"] # ECS Backend → MySQL 3306
    self             = false
    to_port          = 3306
  }]
  name   = "memme-db-sg"
  region = "ap-northeast-2"

  tags = {
    Name = "memme-db-sg"
  }

  vpc_id = aws_vpc.memme.id
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_security_group" "memme_backend_sg" {
  description = "memme-backend-sg"
  egress = [{
    cidr_blocks      = ["0.0.0.0/0"]
    description      = "HTTPS - SSM ECR updates and external APIs"
    from_port        = 443
    ipv6_cidr_blocks = []
    prefix_list_ids  = []
    protocol         = "tcp"
    security_groups  = []
    self             = false
    to_port          = 443
    }, {
    cidr_blocks      = ["0.0.0.0/0"]
    description      = "Ubuntu package repositories - HTTP"
    from_port        = 80
    ipv6_cidr_blocks = []
    prefix_list_ids  = []
    protocol         = "tcp"
    security_groups  = []
    self             = false
    to_port          = 80
    }, {
    cidr_blocks      = []
    description      = "AI API to memme-ai-sg only"
    from_port        = 8000
    ipv6_cidr_blocks = []
    prefix_list_ids  = []
    protocol         = "tcp"
    security_groups  = ["sg-02edb6749fab0e3f7"]
    self             = false
    to_port          = 8000
    }, {
    cidr_blocks      = []
    description      = "MySQL to memme-db-sg only"
    from_port        = 3306
    ipv6_cidr_blocks = []
    prefix_list_ids  = []
    protocol         = "tcp"
    security_groups  = ["sg-0abe0dc2d5f6db0e6"]
    self             = false
    to_port          = 3306
  }]
  ingress = [{
    cidr_blocks      = ["0.0.0.0/0"]
    description      = "http"
    from_port        = 80
    ipv6_cidr_blocks = []
    prefix_list_ids  = []
    protocol         = "tcp"
    security_groups  = []
    self             = false
    to_port          = 80
    }, {
    cidr_blocks      = ["0.0.0.0/0"]
    description      = "https"
    from_port        = 443
    ipv6_cidr_blocks = []
    prefix_list_ids  = []
    protocol         = "tcp"
    security_groups  = []
    self             = false
    to_port          = 443
    }, {
    cidr_blocks      = []
    description      = "AI to backend internal API"
    from_port        = 8080
    ipv6_cidr_blocks = []
    prefix_list_ids  = []
    protocol         = "tcp"
    security_groups  = ["sg-02edb6749fab0e3f7"]
    self             = false
    to_port          = 8080
  }]
  name   = "memme-backend-sg"
  region = "ap-northeast-2"

  tags = {
    Name  = "memme-backend-sg"
    memme = "backend"
  }

  vpc_id = aws_vpc.memme.id
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_security_group" "memme_ai_sg" {
  description = "memme-ai-sg"
  egress = [{
    cidr_blocks      = ["0.0.0.0/0"]
    description      = "HTTPS - SSM ECR updates and external APIs"
    from_port        = 443
    ipv6_cidr_blocks = []
    prefix_list_ids  = []
    protocol         = "tcp"
    security_groups  = []
    self             = false
    to_port          = 443
    }, {
    cidr_blocks      = ["0.0.0.0/0"]
    description      = "Ubuntu package repositories - HTTP"
    from_port        = 80
    ipv6_cidr_blocks = []
    prefix_list_ids  = []
    protocol         = "tcp"
    security_groups  = []
    self             = false
    to_port          = 80
    }, {
    cidr_blocks      = []
    description      = "AI to backend internal API"
    from_port        = 8080
    ipv6_cidr_blocks = []
    prefix_list_ids  = []
    protocol         = "tcp"
    security_groups  = ["sg-0d99aedfebba0f029", "sg-010fbd5aa0b0c5651"] # 기존 EC2 + ECS 내부 API 8080
    self             = false
    to_port          = 8080
    }, {
    cidr_blocks      = []
    description      = "MySQL to memme-db-sg only"
    from_port        = 3306
    ipv6_cidr_blocks = []
    prefix_list_ids  = []
    protocol         = "tcp"
    security_groups  = ["sg-0abe0dc2d5f6db0e6"]
    self             = false
    to_port          = 3306
  }]
  ingress = [{
    cidr_blocks      = []
    description      = "AI API"
    from_port        = 8000
    ipv6_cidr_blocks = []
    prefix_list_ids  = []
    protocol         = "tcp"
    security_groups  = ["sg-0d99aedfebba0f029"]
    self             = false
    to_port          = 8000
    }, {
    cidr_blocks      = []
    description      = ""
    from_port        = 8000
    ipv6_cidr_blocks = []
    prefix_list_ids  = []
    protocol         = "tcp"
    security_groups  = ["sg-010fbd5aa0b0c5651"] # ECS Backend → AI API 8000
    self             = false
    to_port          = 8000
  }]
  name   = "memme-ai-sg"
  region = "ap-northeast-2"

  tags = {
    Name  = "memme-ai-sg"
    memme = "ai"
  }

  vpc_id = aws_vpc.memme.id
  lifecycle {
    prevent_destroy = true
  }
}
