// =============================================================================
// 02_storage_account.bicep
// Deploying a real Azure resource: Storage Account.
// Covers: resource syntax, properties, SKU/kind, tags, dependsOn, outputs.
// Deploy: az deployment group create -g <rg> -f 02_storage_account.bicep
// =============================================================================

param location string = resourceGroup().location
param env      string = 'dev'

// uniqueString gives a stable 13-char hash — storage account names must be:
//   - globally unique across all of Azure
//   - 3–24 characters, lowercase letters and digits ONLY
var storageName = 'sa${uniqueString(resourceGroup().id)}${env}'
// '${...}' is string interpolation; the result here might be: 'saabcdef1234567dev'

var tags = {
  environment: env
  managedBy:   'bicep'
}


// =============================================================================
// RESOURCE DECLARATION — the core of every Bicep file
// =============================================================================
// Syntax:
//   resource <symbolicName> '<resourceType>@<apiVersion>' = {
//     <ARM properties>
//   }
//
// <symbolicName>  — a Bicep-only name used to reference this resource INSIDE
//                   this file.  Not stored in Azure.  camelCase by convention.
// <resourceType>  — the ARM provider + type, e.g. 'Microsoft.Storage/storageAccounts'
// <apiVersion>    — the date-versioned API to use.  Find valid versions with:
//                   az provider show -n Microsoft.Storage --query "resourceTypes[?resourceType=='storageAccounts'].apiVersions"
//                   Always pin to a specific version so behaviour is stable.

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name:     storageName           // 'name' is the actual Azure resource name
  location: location              // Azure region

  // 'tags' is available on almost every ARM resource
  tags: tags

  // 'sku' defines the pricing tier and replication model
  sku: {
    name: 'Standard_LRS'         // Standard_LRS  = locally redundant storage (cheapest)
                                  // Standard_GRS  = geo-redundant (replicates to paired region)
                                  // Standard_RAGRS = read-access geo-redundant
                                  // Premium_LRS    = SSD-backed, low latency
                                  // Premium_ZRS    = zone-redundant SSD
  }

  // 'kind' selects the storage account variant
  kind: 'StorageV2'              // StorageV2      = general purpose v2 (use this for new accounts)
                                  // BlobStorage     = blob-only (no queues/tables)
                                  // FileStorage     = Azure Files (premium)
                                  // BlockBlobStorage = high-throughput block blobs

  // 'properties' is the main config block — differs per resource type
  properties: {
    accessTier: 'Hot'            // Hot  = frequent access (higher storage cost, lower read cost)
                                  // Cool = infrequent access (lower storage, higher read cost)
                                  // Archive = long-term archiving (no instant access)

    supportsHttpsTrafficOnly: true   // reject all plain HTTP requests — always set this to true

    allowBlobPublicAccess: false     // disable anonymous public blob access — security best practice

    minimumTlsVersion: 'TLS1_2'     // reject TLS 1.0/1.1 connections — required by most compliance frameworks

    // Soft delete keeps blobs for N days after deletion (protects against accidental delete)
    // blobServiceProperties is a CHILD resource but can be expressed inline here too
    // (the child resource approach is shown further down)

    networkAcls: {                   // firewall rules
      defaultAction: 'Deny'         // block all traffic by default
      bypass: 'AzureServices'       // allow trusted Azure services (e.g. Azure Backup, Monitor)
      // Add virtualNetworkRules or ipRules here to allow specific networks/IPs
      virtualNetworkRules: []
      ipRules: []
    }

    encryption: {                    // data-at-rest encryption (always on, but you can customise)
      services: {
        blob: { enabled: true }
        file: { enabled: true }
      }
      keySource: 'Microsoft.Storage' // 'Microsoft.Storage' = Microsoft-managed keys (default)
                                      // 'Microsoft.Keyvault' = customer-managed keys (CMK)
    }
  }
}


// --- Child resource — Blob Service ---
// Some resources have CHILD resources (sub-resources).
// The child's name must be PREFIXED with the parent's name + '/'.
// The 'parent:' keyword links them — Bicep handles the naming and dependency automatically.

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-01-01' = {
  parent: storageAccount          // 'parent:' = link to the symbolic name above
                                  // Bicep automatically makes this deploy AFTER the parent
                                  // and prefixes the name: '<storageName>/default'
  name: 'default'                 // blob service sub-resource is always named 'default'

  properties: {
    deleteRetentionPolicy: {
      enabled: true
      days:    7                  // keep deleted blobs for 7 days
    }
    containerDeleteRetentionPolicy: {
      enabled: true
      days:    7
    }
  }
}


// --- Another child — a Blob Container ---
resource dataContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  parent: blobService             // parent is the blobService above (grandchild of storageAccount)
  name:   'data'                  // container name (lowercase, letters/digits/hyphens only)

  properties: {
    publicAccess: 'None'          // 'None' = private (always use this unless you NEED public access)
                                  // 'Blob' = anonymous read for blobs (URLs are guessable)
                                  // 'Container' = anonymous list + read (dangerous)
  }
}


// =============================================================================
// REFERENCING A DEPLOYED RESOURCE
// =============================================================================
// Once a resource is declared, you access its properties via the symbolic name.
// Bicep (and ARM) automatically infer dependencies — if you reference resource A
// inside resource B's properties, Azure deploys A first.

// storageAccount.id             — the full ARM resource ID
// storageAccount.name           — the name (same as storageName var)
// storageAccount.apiVersion     — the API version string
// storageAccount.type           — 'Microsoft.Storage/storageAccounts'
// storageAccount.properties.*   — any property returned by the ARM API

// listKeys() is a Bicep function that calls the ARM list-keys API at deploy time.
// It returns the storage account access keys.
var storageKey = storageAccount.listKeys().keys[0].value
// [0] = first key, .value = the actual key string
// This is a @secure() value automatically — Bicep doesn't log it


// =============================================================================
// OUTPUTS
// =============================================================================

output storageAccountId   string = storageAccount.id
output storageAccountName string = storageAccount.name

// Primary endpoint for blob operations
output blobEndpoint string = storageAccount.properties.primaryEndpoints.blob
// Returns something like: 'https://saabcdef1234567dev.blob.core.windows.net/'

output containerName string = dataContainer.name

@secure()
output storageKey string = storageKey   // @secure() = not logged or displayed


// =============================================================================
// EXERCISES
// =============================================================================
// 1. Add a parameter 'allowedIpAddress' (string, default '').
//    When non-empty, add it to networkAcls.ipRules so only that IP can access the account.
//    Hint: ipRules format is: [ { value: allowedIpAddress, action: 'Allow' } ]
//    Hint: use a conditional (see 05_conditions.bicep) or just set it statically for now.
//
// 2. Add a second container called 'logs' next to the 'data' container.
//    It should also be private.  What does its 'parent:' point to?
//
// 3. Add an output 'tableEndpoint' that exposes the table storage endpoint.
//    Hint: it's at storageAccount.properties.primaryEndpoints.table
//    Why might you want to output endpoints rather than compute the URL yourself?
