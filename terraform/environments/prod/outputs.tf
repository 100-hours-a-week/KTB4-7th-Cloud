output "backend_instance_id" {
  value = aws_instance.backend_server.id
}
output "ai_instance_id" {
  value = aws_instance.ai_server.id
}
output "database_endpoint" {
  value = aws_db_instance.memme_mysql.address
}
output "uploads_bucket_name" {
  value = aws_s3_bucket.uploads.id
}
