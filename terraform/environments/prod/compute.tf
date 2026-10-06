# Existing production resources; adoption only.

resource "aws_eip" "eipalloc_0abbf41bc8c1db381" {



  domain               = "vpc"
  instance             = aws_instance.backend_server.id
  network_border_group = "ap-northeast-2"

  public_ipv4_pool = "amazon"
  region           = "ap-northeast-2"
  tags = {
    Name = "memme-backend-v1"
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_instance" "backend_server" {
  ami                                  = "ami-0bc151a94289adb52"
  associate_public_ip_address          = true
  availability_zone                    = "ap-northeast-2a"
  disable_api_stop                     = false
  disable_api_termination              = false
  ebs_optimized                        = true
  force_destroy                        = false
  get_password_data                    = false
  hibernation                          = false
  iam_instance_profile                 = aws_iam_instance_profile.backendec2role.name
  instance_initiated_shutdown_behavior = "stop"
  instance_type                        = "t3.medium"


  monitoring                 = false
  placement_partition_number = 0
  private_ip                 = "10.0.1.220"
  region                     = "ap-northeast-2"
  secondary_private_ips      = []

  source_dest_check = true
  subnet_id         = aws_subnet.subnet_023daf75ba6f1dfe5.id
  tags = {
    Name  = "backend-server"
    memme = "memme-backend-server"
  }

  tenancy = "default"

  vpc_security_group_ids = [aws_security_group.memme_backend_sg.id]
  capacity_reservation_specification {
    capacity_reservation_preference = "open"
  }
  cpu_options {
    core_count       = 1
    threads_per_core = 2
  }
  credit_specification {
    cpu_credits = "unlimited"
  }
  enclave_options {
    enabled = false
  }
  maintenance_options {
    auto_recovery = "default"
  }
  metadata_options {
    http_endpoint               = "enabled"
    http_protocol_ipv6          = "disabled"
    http_put_response_hop_limit = 2
    http_tokens                 = "required"
    instance_metadata_tags      = "disabled"
  }

  private_dns_name_options {
    enable_resource_name_dns_a_record    = false
    enable_resource_name_dns_aaaa_record = false
    hostname_type                        = "ip-name"
  }
  root_block_device {
    delete_on_termination = true
    encrypted             = true
    iops                  = 3000
    kms_key_id            = "arn:aws:kms:ap-northeast-2:613538400341:key/cd1667d4-08e2-4424-9752-7b652631aca6"
    tags                  = {}

    throughput  = 125
    volume_size = 20
    volume_type = "gp3"
  }
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_instance" "ai_server" {
  ami                                  = "ami-0bc151a94289adb52"
  associate_public_ip_address          = true
  availability_zone                    = "ap-northeast-2a"
  disable_api_stop                     = false
  disable_api_termination              = false
  ebs_optimized                        = true
  force_destroy                        = false
  get_password_data                    = false
  hibernation                          = false
  iam_instance_profile                 = aws_iam_instance_profile.aiec2role.name
  instance_initiated_shutdown_behavior = "stop"
  instance_type                        = "t3.medium"


  monitoring                 = false
  placement_partition_number = 0
  private_ip                 = "10.0.1.236"
  region                     = "ap-northeast-2"
  secondary_private_ips      = []

  source_dest_check = true
  subnet_id         = aws_subnet.subnet_023daf75ba6f1dfe5.id
  tags = {
    Name  = "ai-server"
    memme = "memme-ai-server"
  }

  tenancy = "default"

  vpc_security_group_ids = [aws_security_group.memme_ai_sg.id]
  capacity_reservation_specification {
    capacity_reservation_preference = "open"
  }
  cpu_options {
    core_count       = 1
    threads_per_core = 2
  }
  credit_specification {
    cpu_credits = "unlimited"
  }
  enclave_options {
    enabled = false
  }
  maintenance_options {
    auto_recovery = "default"
  }
  metadata_options {
    http_endpoint               = "enabled"
    http_protocol_ipv6          = "disabled"
    http_put_response_hop_limit = 2
    http_tokens                 = "required"
    instance_metadata_tags      = "disabled"
  }

  private_dns_name_options {
    enable_resource_name_dns_a_record    = false
    enable_resource_name_dns_aaaa_record = false
    hostname_type                        = "ip-name"
  }
  root_block_device {
    delete_on_termination = true
    encrypted             = true
    iops                  = 3000
    kms_key_id            = "arn:aws:kms:ap-northeast-2:613538400341:key/cd1667d4-08e2-4424-9752-7b652631aca6"
    tags                  = {}

    throughput  = 125
    volume_size = 20
    volume_type = "gp3"
  }
  lifecycle {
    prevent_destroy = true
  }
}
