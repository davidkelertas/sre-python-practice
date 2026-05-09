// =============================================================================
// modules/storage.bicep
// Reusable Storage Account module — called by 06_modules.bicep.
// Callers pass params in; outputs expose the key values callers need.
// =============================================================================

// --- Parameters (the module's "API") ---
// Every value the caller can control must be a param.
// Params with defaults are optional; params without defaults are required.

@description('Azure region to deploy into.')
param location string              // required — caller must supply this

@description('Environment name: dev, staging, or prod.')
@allowed(['dev', 'staging', 'prod'])
param env string                   // required

@description('Short application name used in resource naming.')
@minLength(2)
@maxLength(10)
param appName string = 'app'      // optional — defaults to 'app'


// --- Internal variables (not visible to the caller) ---
var saName = toLower('sa${appName}${uniqueString(resourceGroup().id)}${env}')
// storage account names: lowercase letters and digits only, 3-24 chars
// uniqueString() ensures global uniqueness per resource group + env combination

var isProd = env == 'prod'        // convenience bool


// --- The resource this module manages ---
resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name:     saName
  location: location

  sku: {
    // Geo-redundant in prod so a regional failure doesn't lose data
    // Locally redundant in dev/staging — cheaper, sufficient for non-production
    name: isProd ? 'Standard_GRS' : 'Standard_LRS'
  }

  kind: 'StorageV2'    // general purpose v2 — use for all new accounts

  properties: {
    supportsHttpsTrafficOnly: true     // reject plain HTTP — always on
    allowBlobPublicAccess:    false    // no anonymous public access
    minimumTlsVersion:        'TLS1_2'
    accessTier: 'Hot'
  }

  tags: {
    environment: env
    application: appName
    managedBy:   'bicep'
  }
}

// Blob service — needed so we can configure soft-delete
resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-01-01' = {
  parent: storageAccount
  name:   'default'
  properties: {
    deleteRetentionPolicy: {
      enabled: true
      days:    isProd ? 30 : 7    // longer retention in prod
    }
  }
}


// --- Outputs (the module's return values) ---
// Callers access these as:  module.<symbolicName>.outputs.<outputName>

@description('ARM resource ID of the storage account.')
output storageAccountId string = storageAccount.id

@description('Name of the deployed storage account.')
output storageAccountName string = storageAccount.name

@description('Primary blob endpoint URL.')
output blobEndpoint string = storageAccount.properties.primaryEndpoints.blob

@description('The SKU name that was applied.')
output skuName string = storageAccount.sku.name
