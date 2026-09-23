using './main.bicep'

// =============================================================================
// Foundry Enterprise Demo — Sweden Central
// Template 19 (private network + agent tools) against a pre-created BYO VNet
// =============================================================================

param location = 'swedencentral'
param aiServices = 'aifoundrydemo'
param firstProjectName = 'insurance'
param projectDescription = 'Insurance enterprise demo — network-secured Foundry agents'
param displayName = 'Insurance Demo'

// ---------------------------------------------------------------------------
// Model deployment
// ---------------------------------------------------------------------------
param modelName = 'gpt-4.1'
param modelFormat = 'OpenAI'
param modelVersion = '2025-04-14'
param modelSkuName = 'GlobalStandard'
param modelCapacity = 50

// ---------------------------------------------------------------------------
// Networking — reuse the pre-created VNet and all three subnets as-is.
// Subnets are referenced, never modified (shared/peered VNet).
// ---------------------------------------------------------------------------
param existingVnetResourceId = '/subscriptions/b55aa044-0dd2-46bf-9ef5-31d5c3dee20c/resourceGroups/rg-foundry-demo/providers/Microsoft.Network/virtualNetworks/vnet-foundry-demo'
param existingAgentSubnetResourceId = '/subscriptions/b55aa044-0dd2-46bf-9ef5-31d5c3dee20c/resourceGroups/rg-foundry-demo/providers/Microsoft.Network/virtualNetworks/vnet-foundry-demo/subnets/agent-subnet'
param existingPeSubnetResourceId = '/subscriptions/b55aa044-0dd2-46bf-9ef5-31d5c3dee20c/resourceGroups/rg-foundry-demo/providers/Microsoft.Network/virtualNetworks/vnet-foundry-demo/subnets/pe-subnet'
param existingMcpSubnetResourceId = '/subscriptions/b55aa044-0dd2-46bf-9ef5-31d5c3dee20c/resourceGroups/rg-foundry-demo/providers/Microsoft.Network/virtualNetworks/vnet-foundry-demo/subnets/mcp-subnet'

// ---------------------------------------------------------------------------
// BYO backing resources — create new (clean demo blast radius)
// ---------------------------------------------------------------------------
param existingAiSearchResourceId = ''
param existingAzureStorageAccountResourceId = ''
param existingAzureCosmosDBAccountResourceId = ''
param existingFabricWorkspaceResourceId = ''

// Private ACR for hosted agent images
param enableContainerRegistry = true
param developerIpCidr = ''

// ---------------------------------------------------------------------------
// Private DNS zones
// Reuse the shared landing-zone zones (already linked to vnet-foundry-demo).
// 'privatelink.fabric.microsoft.com' does not exist in the landing zone, so it
// is left blank and created in this deployment's RG.
// ---------------------------------------------------------------------------
param existingDnsZones = {
  'privatelink.services.ai.azure.com': { subscriptionId: '', resourceGroup: 'rg-ai-landing-zone' }
  'privatelink.openai.azure.com': { subscriptionId: '', resourceGroup: 'rg-ai-landing-zone' }
  'privatelink.cognitiveservices.azure.com': { subscriptionId: '', resourceGroup: 'rg-ai-landing-zone' }
  'privatelink.search.windows.net': { subscriptionId: '', resourceGroup: 'rg-ai-landing-zone' }
  'privatelink.blob.core.windows.net': { subscriptionId: '', resourceGroup: 'rg-ai-landing-zone' }
  'privatelink.documents.azure.com': { subscriptionId: '', resourceGroup: 'rg-ai-landing-zone' }
  'privatelink.azurecr.io': { subscriptionId: '', resourceGroup: 'rg-ai-landing-zone' }
  'privatelink.fabric.microsoft.com': { subscriptionId: '', resourceGroup: '' }
}

// Azure Monitor zones do not exist in the landing zone — create locally and let
// the template manage their VNet links.
param existingMonitorDnsZones = {
  'privatelink.monitor.azure.com': { subscriptionId: '', resourceGroup: '' }
  'privatelink.oms.opinsights.azure.com': { subscriptionId: '', resourceGroup: '' }
  'privatelink.ods.opinsights.azure.com': { subscriptionId: '', resourceGroup: '' }
  'privatelink.agentsvc.azure-automation.net': { subscriptionId: '', resourceGroup: '' }
}
