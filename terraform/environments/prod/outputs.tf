output "ai_instance_id" {
  value = aws_instance.ai_server.id
}
output "uploads_bucket_name" {
  value = aws_s3_bucket.uploads.id
}
