// =============================================================================
// modules/monitoring.bicep
// Log Analytics Workspace + Application Insights module.
// Called by 06_modules.bicep — demonstrates dependsOn and array params.
// =============================================================================

@description('Azure region.')
param location string

@description('Environment name.')
param env string = 'dev'

@description('ARM resource IDs of resources to send diagnostic logs from.')
param targetResourceIds array = []    // optional — empty array = deploy workspace only, no diag settings

@description('Log retention in days (30-730).')
@minValue(30)
@maxValue(730)
param retentionDays int = 90


var workspaceName = 'law-${env}-${uniqueString(resourceGroup().id)}'
var appInsightsName = 'appi-${env}-${uniqueString(resourceGroup().id)}'
var isProd = env == 'prod'


// --- Log Analytics Workspace ---
// The central store for logs, metrics, and traces from all your resources.
// Query language: KQL (Kusto Query Language) — similar to SQL but designed for logs.
resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name:     workspaceName
  location: location
  tags:     { environment: env }

  properties: {
    sku: {
      name: 'PerGB2018'    // PerGB2018 = pay per GB ingested — standard SKU for new workspaces
                            // Legacy SKUs: Free (500MB/day cap), Standard, Premium — avoid these
    }
    retentionInDays: retentionDays   // how long queried data is available

    features: {
      // Workspace-level access control: users see logs only from resources they can RBAC-access
      // The alternative (false) = anyone with workspace access sees ALL logs (less secure)
      enableLogAccessUsingOnlyResourcePermissions: isProd
    }

    // publicNetworkAccessForIngestion/Query: restrict to private endpoints in prod
    publicNetworkAccessForIngestion: isProd ? 'Disabled' : 'Enabled'
    publicNetworkAccessForQuery:     isProd ? 'Disabled' : 'Enabled'
  }
}


// --- Application Insights ---
// APM (Application Performance Monitoring) tool — traces, requests, exceptions, dependencies.
// Requires a Log Analytics workspace as its backend (workspace-based mode, 2020+).
resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name:     appInsightsName
  location: location
  tags:     { environment: env }

  kind: 'web'    // 'web' covers web apps, APIs; also valid: 'other', 'ios', 'java', 'phone'

  properties: {
    Application_Type: 'web'              // type for the portal UI
    WorkspaceResourceId: workspace.id    // link to our Log Analytics workspace (workspace-based mode)
    // workspace-based mode is required for new resources — classic (non-workspace) is retiring
    RetentionInDays: retentionDays
    IngestionMode: 'LogAnalytics'        // send data to the linked workspace (not classic storage)
    publicNetworkAccessForIngestion: isProd ? 'Disabled' : 'Enabled'
    publicNetworkAccessForQuery:     isProd ? 'Disabled' : 'Enabled'
  }
}


// --- Diagnostic Settings for each target resource ---
// Loop: for every resource ID in targetResourceIds, create a diagnostic setting
// that routes its logs + metrics to our new workspace.
//
// This is why 06_modules.bicep uses dependsOn: [networking] on this module —
// the networking module creates resources that we want to monitor, but we don't
// actually reference their outputs here (we receive IDs via the targetResourceIds param).

resource diagSettings 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = [
  for (resourceId, i) in targetResourceIds: {    // loop with index — 'i' gives a unique name suffix
    // 'scope' using a resourceId string — this is the only way to scope to a resource
    // whose type we don't know at author time
    name:  'diag-to-law-${i}'
    scope: resourceGroup()    // diagnostic settings must be deployed at the resource group scope
                              // (the actual target is controlled by the resourceId in properties)

    properties: {
      // The resource to collect diagnostics FROM:
      // NOTE: In real Bicep, diagnosticSettings scope to a specific resource.
      // Here we show the pattern — in practice you'd use 'existing' to reference
      // each resource by ID and set scope: thatResource.
      workspaceId: workspace.id    // send all logs/metrics to our workspace

      // Enable all available log categories and metrics
      // (In production, be selective — ingesting everything can be expensive)
      logs: [
        {
          categoryGroup: 'allLogs'    // shorthand: enable ALL log categories for this resource
          enabled:       true
        }
      ]
      metrics: [
        {
          category: 'AllMetrics'
          enabled:  true
        }
      ]
    }
  }
]


// --- Outputs ---
output workspaceId           string = workspace.id
output workspaceName         string = workspace.name
output appInsightsId         string = appInsights.id
output appInsightsName       string = appInsights.name

@description('Connection string for the SDK — set as APPLICATIONINSIGHTS_CONNECTION_STRING env var.')
output appInsightsConnectionString string = appInsights.properties.ConnectionString
// Connection strings replace the older instrumentation key — use this in new apps.

@description('Instrumentation key (legacy — prefer connection string).')
output instrumentationKey string = appInsights.properties.InstrumentationKey
