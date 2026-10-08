# Existing production resources; adoption only.

resource "aws_route_table" "rtb_0b431ab9301b9009b" {
  propagating_vgws = []
  region           = "ap-northeast-2"
  route            = []
  tags             = {}

  vpc_id = aws_vpc.memme.id
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_subnet" "subnet_023daf75ba6f1dfe5" {
  assign_ipv6_address_on_creation = false
  availability_zone               = "ap-northeast-2a"

  cidr_block = "10.0.1.0/24"

  enable_dns64 = false

  enable_resource_name_dns_a_record_on_launch    = false
  enable_resource_name_dns_aaaa_record_on_launch = false



  ipv6_native = false

  map_public_ip_on_launch = true

  private_dns_hostname_type_on_launch = "ip-name"
  region                              = "ap-northeast-2"
  tags = {
    Name  = "memme-public-subnet-a"
    memme = "public-subnet-a"
  }

  vpc_id = aws_vpc.memme.id
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_subnet" "subnet_0f80faec15de9dffc" {
  assign_ipv6_address_on_creation = false
  availability_zone               = "ap-northeast-2a"

  cidr_block = "10.0.11.0/24"

  enable_dns64 = false

  enable_resource_name_dns_a_record_on_launch    = false
  enable_resource_name_dns_aaaa_record_on_launch = false



  ipv6_native = false

  map_public_ip_on_launch = false

  private_dns_hostname_type_on_launch = "ip-name"
  region                              = "ap-northeast-2"
  tags = {
    Name  = "memme-db-subnet-a"
    memme = "db-subnet-a"
  }

  vpc_id = aws_vpc.memme.id
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_internet_gateway" "memme" {
  region = "ap-northeast-2"
  tags = {
    Name  = "memme-igw"
    memme = "memme-igw"
  }

  vpc_id = aws_vpc.memme.id
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_subnet" "subnet_04319b3c278097d7a" {
  assign_ipv6_address_on_creation = false
  availability_zone               = "ap-northeast-2c"

  cidr_block = "10.0.12.0/24"

  enable_dns64 = false

  enable_resource_name_dns_a_record_on_launch    = false
  enable_resource_name_dns_aaaa_record_on_launch = false



  ipv6_native = false

  map_public_ip_on_launch = false

  private_dns_hostname_type_on_launch = "ip-name"
  region                              = "ap-northeast-2"
  tags = {
    Name  = "memme-db-subnet-c"
    memme = "db-subnet-c"
  }

  vpc_id = aws_vpc.memme.id
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_route_table" "rtb_042a3283b76eba2d2" {
  propagating_vgws = []
  region           = "ap-northeast-2"
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.memme.id
  }
  tags = {
    Name  = "memme-public-rt"
    memme = "memme-public-rt"
  }

  vpc_id = aws_vpc.memme.id
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_route_table_association" "subnet_023daf75ba6f1dfe5" {

  region         = "ap-northeast-2"
  route_table_id = aws_route_table.rtb_042a3283b76eba2d2.id
  subnet_id      = aws_subnet.subnet_023daf75ba6f1dfe5.id
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_vpc" "memme" {
  assign_generated_ipv6_cidr_block     = false
  cidr_block                           = "10.0.0.0/16"
  enable_dns_hostnames                 = true
  enable_dns_support                   = true
  enable_network_address_usage_metrics = false
  instance_tenancy                     = "default"

  region = "ap-northeast-2"
  tags = {
    Name = "memme-vpc"
  }

  lifecycle {
    prevent_destroy = true
  }
}
