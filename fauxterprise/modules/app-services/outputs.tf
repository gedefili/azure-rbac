output "web_app_identities" {
  description = "Map of web app name → managed identity principal ID"
  value = {
    prod_api      = azurerm_linux_web_app.prod_api.identity[0].principal_id
    prod_frontend = azurerm_linux_web_app.prod_frontend.identity[0].principal_id
    staging_api   = azurerm_linux_web_app.staging_api.identity[0].principal_id
    dev_api       = azurerm_linux_web_app.dev_api.identity[0].principal_id
  }
}

output "function_app_identities" {
  value = {
    event_processor = azurerm_linux_function_app.event_processor.identity[0].principal_id
    data_pipeline   = azurerm_linux_function_app.data_pipeline.identity[0].principal_id
  }
}
