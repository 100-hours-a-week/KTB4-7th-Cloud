# Existing production resources; adoption only.

resource "aws_iam_openid_connect_provider" "github" {
  client_id_list = ["sts.amazonaws.com"]
  tags = {
    Project = "memme"
  }

  thumbprint_list = ["ab9d0263244dd0326eb67015705a667e79cfe998"]
  url             = "https://token.actions.githubusercontent.com"
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_iam_role_policy_attachment" "aiec2role_amazonec2containerregistryreadonly" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
  role       = aws_iam_role.aiec2role.name
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_iam_role_policy_attachment" "aiec2role_amazonssmmanagedinstancecore" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
  role       = aws_iam_role.aiec2role.name
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_iam_role_policy_attachment" "aiec2role_cloudwatchagentserverpolicy" {
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"
  role       = aws_iam_role.aiec2role.name
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_iam_role_policy" "aiec2role_readmemmeairuntimesecret" {
  name = "ReadMemmeAIRuntimeSecret"
  policy = jsonencode({
    Statement = [{
      Action   = "secretsmanager:GetSecretValue"
      Effect   = "Allow"
      Resource = "arn:aws:secretsmanager:ap-northeast-2:613538400341:secret:/memme/prod/ai/runtime-*"
      Sid      = "ReadAIRuntimeSecret"
    }]
    Version = "2012-10-17"
  })
  role = aws_iam_role.aiec2role.name
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_iam_role_policy_attachment" "backendec2role_cloudwatchagentserverpolicy" {
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"
  role       = aws_iam_role.backendec2role.name
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_iam_role_policy_attachment" "backendec2role_amazonssmmanagedinstancecore" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
  role       = aws_iam_role.backendec2role.name
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_iam_role_policy" "githubactionsaiecrpushrole_pushmemmeai" {
  name = "PushMemmeAI"
  policy = jsonencode({
    Statement = [{
      Action   = "ecr:GetAuthorizationToken"
      Effect   = "Allow"
      Resource = "*"
      Sid      = "ECRLogin"
      }, {
      Action   = ["ecr:BatchCheckLayerAvailability", "ecr:InitiateLayerUpload", "ecr:UploadLayerPart", "ecr:CompleteLayerUpload", "ecr:PutImage", "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:DescribeImages"]
      Effect   = "Allow"
      Resource = "arn:aws:ecr:ap-northeast-2:613538400341:repository/memme/ai"
      Sid      = "PushAIRepositoryOnly"
    }]
    Version = "2012-10-17"
  })
  role = aws_iam_role.githubactionsaiecrpushrole.name
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_iam_role_policy" "githubactionsbackendecrpushrole_pushmemmebackend" {
  name = "PushMemmeBackend"
  policy = jsonencode({
    Statement = [{
      Action   = "ecr:GetAuthorizationToken"
      Effect   = "Allow"
      Resource = "*"
      Sid      = "ECRLogin"
      }, {
      Action   = ["ecr:BatchCheckLayerAvailability", "ecr:InitiateLayerUpload", "ecr:UploadLayerPart", "ecr:CompleteLayerUpload", "ecr:PutImage", "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:DescribeImages"]
      Effect   = "Allow"
      Resource = "arn:aws:ecr:ap-northeast-2:613538400341:repository/memme/backend"
      Sid      = "PushBackendRepositoryOnly"
    }]
    Version = "2012-10-17"
  })
  role = aws_iam_role.githubactionsbackendecrpushrole.name
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_iam_instance_profile" "aiec2role" {
  name = aws_iam_role.aiec2role.name
  path = "/"
  role = aws_iam_role.aiec2role.name
  tags = {}

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_iam_role" "aiec2role" {
  assume_role_policy = jsonencode({
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ec2.amazonaws.com"
      }
    }]
    Version = "2012-10-17"
  })
  description           = "AIEC2Role - Allows EC2 instances to call AWS services on your behalf."
  force_detach_policies = false
  max_session_duration  = 3600
  name                  = "AIEC2Role"
  path                  = "/"

  tags = {}

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_iam_role_policy_attachment" "backendec2role_amazonec2containerregistryreadonly" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
  role       = aws_iam_role.backendec2role.name
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_iam_role" "githubactionsclouddeployrole" {
  assume_role_policy = jsonencode({
    Statement = [{
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud"         = "sts.amazonaws.com"
          "token.actions.githubusercontent.com:environment" = "production"
          "token.actions.githubusercontent.com:ref"         = "refs/heads/main"
          "token.actions.githubusercontent.com:sub"         = "repo:100-hours-a-week@167328634/KTB4-7th-Cloud@1344636758:environment:production"
        }
      }
      Effect = "Allow"
      Principal = {
        Federated = "arn:aws:iam::613538400341:oidc-provider/token.actions.githubusercontent.com"
      }
    }]
    Version = "2012-10-17"
  })
  description           = "Allows only KTB4-7th-Cloud main to deploy approved ECR images through SSM."
  force_detach_policies = false
  max_session_duration  = 3600
  name                  = "GitHubActionsCloudDeployRole"
  path                  = "/"

  tags = {}

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_iam_role" "backendec2role" {
  assume_role_policy = jsonencode({
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ec2.amazonaws.com"
      }
    }]
    Version = "2012-10-17"
  })
  description           = "BackendEC2Role - Allows EC2 instances to call AWS services on your behalf."
  force_detach_policies = false
  max_session_duration  = 3600
  name                  = "BackendEC2Role"
  path                  = "/"

  tags = {}

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_iam_role_policy" "backendec2role_readmemmebackendruntimesecret" {
  name = "ReadMemmeBackendRuntimeSecret"
  policy = jsonencode({
    Statement = [{
      Action   = "secretsmanager:GetSecretValue"
      Effect   = "Allow"
      Resource = "arn:aws:secretsmanager:ap-northeast-2:613538400341:secret:/memme/prod/backend/runtime-*"
      Sid      = "ReadBackendRuntimeSecret"
    }]
    Version = "2012-10-17"
  })
  role = aws_iam_role.backendec2role.name
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_iam_role" "githubactionsbackendecrpushrole" {
  assume_role_policy = jsonencode({
    Statement = [{
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          "token.actions.githubusercontent.com:sub" = "repo:100-hours-a-week@167328634/KTB4-7th-BE@1344635802:ref:refs/heads/dev"
        }
      }
      Effect = "Allow"
      Principal = {
        Federated = "arn:aws:iam::613538400341:oidc-provider/token.actions.githubusercontent.com"
      }
      Sid = "GitHubBackendDevOnly"
    }]
    Version = "2012-10-17"
  })
  description           = "GitHub Actions KTB4-7th-BE dev: push and pull memme/backend only"
  force_detach_policies = false
  max_session_duration  = 3600
  name                  = "GitHubActionsBackendECRPushRole"
  path                  = "/"

  tags = {
    Project    = "memme"
    Repository = "100-hours-a-week/KTB4-7th-BE"
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_iam_role_policy" "githubactionsclouddeployrole_memmeclouddeploymentpolicy" {
  name = "MemmeCloudDeploymentPolicy"
  policy = jsonencode({
    Statement = [{
      Action   = "ecr:DescribeImages"
      Effect   = "Allow"
      Resource = ["arn:aws:ecr:ap-northeast-2:613538400341:repository/memme/backend", "arn:aws:ecr:ap-northeast-2:613538400341:repository/memme/ai"]
      Sid      = "ReadApprovedMemmeImages"
      }, {
      Action   = "ssm:SendCommand"
      Effect   = "Allow"
      Resource = ["arn:aws:ssm:ap-northeast-2::document/AWS-RunShellScript", "arn:aws:ec2:ap-northeast-2:613538400341:instance/i-0ffc5f41db72dac30", "arn:aws:ec2:ap-northeast-2:613538400341:instance/i-06c4c159ed4155c70"]
      Sid      = "DeployOnlyToMemmeInstances"
      }, {
      Action   = "ssm:GetCommandInvocation"
      Effect   = "Allow"
      Resource = "*"
      Sid      = "ReadDeploymentCommandStatus"
    }]
    Version = "2012-10-17"
  })
  role = aws_iam_role.githubactionsclouddeployrole.name
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_iam_role" "githubactionsaiecrpushrole" {
  assume_role_policy = jsonencode({
    Statement = [{
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          "token.actions.githubusercontent.com:sub" = "repo:100-hours-a-week@167328634/KTB4-7th-AI@1344636282:ref:refs/heads/dev"
        }
      }
      Effect = "Allow"
      Principal = {
        Federated = "arn:aws:iam::613538400341:oidc-provider/token.actions.githubusercontent.com"
      }
      Sid = "GitHubAIDevOnly"
    }]
    Version = "2012-10-17"
  })
  description           = "AI dev GitHub Actions ECR push only"
  force_detach_policies = false
  max_session_duration  = 3600
  name                  = "GitHubActionsAIECRPushRole"
  path                  = "/"

  tags = {
    Project    = "memme"
    Repository = "100-hours-a-week/KTB4-7th-AI"
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_iam_role_policy" "backendec2role_memmesalesstorageaccess" {
  name = "MemmeSalesStorageAccess"
  policy = jsonencode({
    Statement = [{
      Action   = ["s3:PutObject", "s3:GetObject"]
      Effect   = "Allow"
      Resource = "arn:aws:s3:::memme-sales-uploads-613538400341/*"
      Sid      = "ReadWriteSalesUploads"
    }]
    Version = "2012-10-17"
  })
  role = aws_iam_role.backendec2role.name
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_iam_instance_profile" "backendec2role" {
  name = aws_iam_role.backendec2role.name
  path = "/"
  role = aws_iam_role.backendec2role.name
  tags = {}

  lifecycle {
    prevent_destroy = true
  }
}
