// =============================================================================
// modules/appservice.bicep
// App Service Plan + Web App module — called by 06_modules.bicep.
// Demonstrates: consuming outputs from other modules (storage name, subnet ID).
// =============================================================================

@description('Azure region.')
param location string

@description('Environment name.')
param env string = 'dev'

@description('Storage account name — passed in from the storage module output.')
param storageAccountName string   // required — comes from storage.outputs.storageAccountName

@description('Subnet ID for VNet Integration — passed in from networking module output.')
param subnetId string             // required — comes from networking.outputs.appSubnetId

@description('App Service SKU.')
@allowed(['B1', 'B2', 'B3', 'S1', 'S2', 'P1v3', 'P2v3'])
param skuName string = 'B1'      // B1 = cheapest paid tier (no custom domains on Free/Shared)


var isProd    = env == 'prod'
var planName  = 'asp-${env}'
var appName   = 'app-${uniqueString(resourceGroup().id)}-${env}'


// --- App Service Plan (the compute capacity) ---
resource appPlan 'Microsoft.Web/serverfarms@2023-01-01' = {
  name:     planName
  location: location
  tags:     { environment: env }

  sku: {
    name: skuName
    // The tier is inferred from the SKU name:
    //   B = Basic, S = Standard, P = Premium
  }

  kind: 'linux'           // 'linux' for Python/Node/containers; omit for Windows

  properties: {
    reserved: true        // reserved: true is REQUIRED for Linux plans
    // Without this, Azure creates a Windows plan even if kind='linux'
  }
}


// --- Web App ---
resource webApp 'Microsoft.Web/sites@2023-01-01' = {
  name:     appName
  location: location
  tags:     { environment: env }

  // Managed identity lets the app authenticate to Azure services without passwords
  identity: {
    type: 'SystemAssigned'
  }

  properties: {
    serverFarmId: appPlan.id    // link to the plan above — Bicep infers dependency

    httpsOnly: true             // redirect all HTTP to HTTPS automatically

    siteConfig: {
      linuxFxVersion: 'PYTHON|3.12'    // runtime stack; format: LANGUAGE|VERSION

      // VNet Integration — route outbound traffic through the app subnet
      // (required to reach private endpoints or resources inside the VNet)
      // Note: this property is set on the networkConfig child resource below

      alwaysOn: isProd          // keep the app warm in prod; allow cold starts in dev (saves cost)

      appSettings: [
        // App settings are environment variables inside the container
        {
          name:  'STORAGE_ACCOUNT_NAME'
          value: storageAccountName    // injected from the caller (storage module output)
        }
        {
          name:  'ENVIRONMENT'
          value: env
        }
        {
          name:  'APPLICATIONINSIGHTS_CONNECTION_STRING'
          value: ''    // would be set to an App Insights resource output in a real deployment
        }
      ]
    }
  }
}

// --- VNet Integration (child resource) ---
// Connects the web app's OUTBOUND traffic to the VNet subnet
resource vnetIntegration 'Microsoft.Web/sites/networkConfig@2023-01-01' = {
  parent: webApp
  name:   'virtualNetwork'           // name is always 'virtualNetwork' for this child type

  properties: {
    subnetResourceId:          subnetId    // the app subnet ID from the networking module
    swiftSupported:            true        // Swift = faster VNet integration for Standard+ plans
  }
}


// --- Outputs ---
output appServicePlanId string = appPlan.id
output webAppName        string = webApp.name
output webAppUrl         string = 'https://${webApp.properties.defaultHostName}'
output principalId       string = webApp.identity.principalId   // for role assignments
