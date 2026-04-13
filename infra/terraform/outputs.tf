output "platform_summary" {
  description = "Normalized install contract for the platform."
  value       = local.install_summary
}

output "ansible_inventory_ini" {
  description = "INI inventory rendered from Terraform inputs."
  value       = local.ansible_inventory_ini
}

output "ansible_extra_vars" {
  description = "Extra vars map consumed by Ansible."
  value       = local.ansible_extra_vars
  sensitive   = true
}

