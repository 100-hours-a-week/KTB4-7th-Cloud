# Existing AWS resources. These imports do not create infrastructure.

import {
  to = aws_vpc.memme
  id = "vpc-068a51a939b1c3207"
}

import {
  to = aws_subnet.subnet_023daf75ba6f1dfe5
  id = "subnet-023daf75ba6f1dfe5"
}

import {
  to = aws_subnet.subnet_0f80faec15de9dffc
  id = "subnet-0f80faec15de9dffc"
}

import {
  to = aws_subnet.subnet_04319b3c278097d7a
  id = "subnet-04319b3c278097d7a"
}

import {
  to = aws_internet_gateway.memme
  id = "igw-0d21b49c0270777b0"
}

import {
  to = aws_route_table.rtb_042a3283b76eba2d2
  id = "rtb-042a3283b76eba2d2"
}

import {
  to = aws_route_table_association.subnet_023daf75ba6f1dfe5
  id = "subnet-023daf75ba6f1dfe5/rtb-042a3283b76eba2d2"
}

import {
  to = aws_route_table.rtb_0b431ab9301b9009b
  id = "rtb-0b431ab9301b9009b"
}

import {
  to = aws_security_group.memme_backend_sg
  id = "sg-0d99aedfebba0f029"
}

import {
  to = aws_security_group.memme_db_sg
  id = "sg-0abe0dc2d5f6db0e6"
}

import {
  to = aws_security_group.memme_ai_sg
  id = "sg-02edb6749fab0e3f7"
}

import {
  to = aws_instance.backend_server
  id = "i-0ffc5f41db72dac30"
}

import {
  to = aws_instance.ai_server
  id = "i-06c4c159ed4155c70"
}

import {
  to = aws_eip.eipalloc_0abbf41bc8c1db381
  id = "eipalloc-0abbf41bc8c1db381"
}

import {
  to = aws_db_instance.memme_mysql
  id = "memme-mysql"
}

import {
  to = aws_db_subnet_group.memme_db_subnet_group
  id = "memme-db-subnet-group"
}

import {
  to = aws_s3_bucket.uploads
  id = "memme-sales-uploads-613538400341"
}

import {
  to = aws_s3_bucket_versioning.memme_sales_uploads_613538400341
  id = "memme-sales-uploads-613538400341"
}

import {
  to = aws_s3_bucket_server_side_encryption_configuration.memme_sales_uploads_613538400341
  id = "memme-sales-uploads-613538400341"
}

import {
  to = aws_s3_bucket_public_access_block.memme_sales_uploads_613538400341
  id = "memme-sales-uploads-613538400341"
}

import {
  to = aws_s3_bucket_ownership_controls.memme_sales_uploads_613538400341
  id = "memme-sales-uploads-613538400341"
}

import {
  to = aws_s3_bucket_lifecycle_configuration.memme_sales_uploads_613538400341
  id = "memme-sales-uploads-613538400341"
}

import {
  to = aws_ecr_repository.memme_ai
  id = "memme/ai"
}

import {
  to = aws_ecr_repository.memme_backend
  id = "memme/backend"
}

import {
  to = aws_iam_instance_profile.aiec2role
  id = "AIEC2Role"
}

import {
  to = aws_iam_instance_profile.backendec2role
  id = "BackendEC2Role"
}

import {
  to = aws_iam_role.aiec2role
  id = "AIEC2Role"
}

import {
  to = aws_iam_role_policy.aiec2role_readmemmeairuntimesecret
  id = "AIEC2Role:ReadMemmeAIRuntimeSecret"
}

import {
  to = aws_iam_role_policy_attachment.aiec2role_cloudwatchagentserverpolicy
  id = "AIEC2Role/arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"
}

import {
  to = aws_iam_role_policy_attachment.aiec2role_amazonssmmanagedinstancecore
  id = "AIEC2Role/arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

import {
  to = aws_iam_role_policy_attachment.aiec2role_amazonec2containerregistryreadonly
  id = "AIEC2Role/arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

import {
  to = aws_iam_role.backendec2role
  id = "BackendEC2Role"
}

import {
  to = aws_iam_role_policy.backendec2role_memmesalesstorageaccess
  id = "BackendEC2Role:MemmeSalesStorageAccess"
}

import {
  to = aws_iam_role_policy.backendec2role_readmemmebackendruntimesecret
  id = "BackendEC2Role:ReadMemmeBackendRuntimeSecret"
}

import {
  to = aws_iam_role_policy_attachment.backendec2role_cloudwatchagentserverpolicy
  id = "BackendEC2Role/arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"
}

import {
  to = aws_iam_role_policy_attachment.backendec2role_amazonssmmanagedinstancecore
  id = "BackendEC2Role/arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

import {
  to = aws_iam_role_policy_attachment.backendec2role_amazonec2containerregistryreadonly
  id = "BackendEC2Role/arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

import {
  to = aws_iam_role.githubactionsaiecrpushrole
  id = "GitHubActionsAIECRPushRole"
}

import {
  to = aws_iam_role_policy.githubactionsaiecrpushrole_pushmemmeai
  id = "GitHubActionsAIECRPushRole:PushMemmeAI"
}

import {
  to = aws_iam_role.githubactionsbackendecrpushrole
  id = "GitHubActionsBackendECRPushRole"
}

import {
  to = aws_iam_role_policy.githubactionsbackendecrpushrole_pushmemmebackend
  id = "GitHubActionsBackendECRPushRole:PushMemmeBackend"
}

import {
  to = aws_iam_role.githubactionsclouddeployrole
  id = "GitHubActionsCloudDeployRole"
}

import {
  to = aws_iam_role_policy.githubactionsclouddeployrole_memmeclouddeploymentpolicy
  id = "GitHubActionsCloudDeployRole:MemmeCloudDeploymentPolicy"
}

import {
  to = aws_iam_openid_connect_provider.github
  id = "arn:aws:iam::613538400341:oidc-provider/token.actions.githubusercontent.com"
}

import {
  to = aws_secretsmanager_secret._memme_prod_backend_runtime
  id = "arn:aws:secretsmanager:ap-northeast-2:613538400341:secret:/memme/prod/backend/runtime-dDbhKg"
}

import {
  to = aws_secretsmanager_secret._memme_prod_ai_runtime
  id = "arn:aws:secretsmanager:ap-northeast-2:613538400341:secret:/memme/prod/ai/runtime-SwQQK9"
}
