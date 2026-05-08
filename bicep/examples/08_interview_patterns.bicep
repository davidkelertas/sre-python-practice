// =============================================================================
// 08_interview_patterns.bicep
// Patterns most likely to come up in a Senior SRE / Platform Engineering interview.
// Covers: existing keyword, Key Vault secret references, resource locks,
//         deployment scripts, diagnostic settings, Private Endpoints, what-if.
// =============================================================================

param location string = resourceGroup().location
param env      string = 'prod'

// =============================================================================
// 1. 'existing' KEYWORD — reference a resource that ALREADY EXISTS in Azure
// =============================================================================
// 'existing' tells Bicep: "this resource is already deployed — don't create it,
// just read its properties so I can reference them."
// The resource must actually exist or the deployment will fail.

// Reference a Key Vault that was deployed by a different team / different template
resource existingKeyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: 'kv-platform-${env}'    // must match the actual resource name in Azure
  // No 'location', no 'properties' — those fields are for creating, not referencing
}

// Reference a VNet in a DIFFERENT resource group
resource sharedVnet 'Microsoft.Network/virtualNetworks@2023-05-01' existing = {
  name:  'vnet-shared-${env}'
  scope: resourceGroup('rg-networking-${env}')  // specify RG when it differs from this deployment's RG
}

// Now you can use existingKeyVault and sharedVnet as if you created them here:
//   existingKeyVault.id             → ARM resource ID
//   existingKeyVault.properties.vaultUri   → 'https://kv-platform-prod.vault.azure.net/'
//   sharedVnet.properties.addressSpace.addressPrefixes[0]   → '10.0.0.0/8'


// =============================================================================
// 2. KEY VAULT SECRET REFERENCES — reading secrets at deploy time
// =============================================================================
// Pattern: Key Vault stores a secret; Bicep reads it during deployment.
// The secret value is passed to a resource property without ever appearing in
// ARM logs, outputs, or template files.

// Reference a specific secret inside the vault
resource dbPasswordSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' existing = {
  parent: existingKeyVault      // parent links to the vault above
  name:   'db-password'         // must match the secret name in Key Vault
}

// Use the secret in a resource:
// dbPasswordSecret.properties.secretUri        — versioned URI (changes on rotation)
// dbPasswordSecret.properties.secretUriWithVersion — explicit versioned URI
//
// Example: pass to an App Service app setting
resource appService 'Microsoft.Web/sites@2023-01-01' = {
  name:     'app-${uniqueString(resourceGroup().id)}'
  location: location
  identity: { type: 'SystemAssigned' }
  properties: {
    serverFarmId: '/subscriptions/${subscription().subscriptionId}/resourceGroups/rg-compute/providers/Microsoft.Web/serverfarms/asp-prod'
    siteConfig: {
      appSettings: [
        {
          name:  'DB_PASSWORD'
          value: '@Microsoft.KeyVault(SecretUri=${dbPasswordSecret.properties.secretUri})'
          // This is a Key Vault Reference — App Service fetches the secret at RUNTIME
          // using the app's managed identity.  The secret value is NEVER stored in the config.
          // When the secret rotates in Key Vault, App Service automatically gets the new value.
        }
      ]
    }
  }
}


// =============================================================================
// 3. RESOURCE LOCKS — prevent accidental deletion
// =============================================================================
// A lock on a resource group or resource prevents deletion (or any modification).
// Use 'CanNotDelete' for prod databases, VNets, etc.
// Locks are inherited: a lock on the RG applies to all resources inside.

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name:     'sa${uniqueString(resourceGroup().id)}'
  location: location
  sku:      { name: 'Standard_GRS' }
  kind:     'StorageV2'
  properties: { supportsHttpsTrafficOnly: true }
}

resource storageLock 'Microsoft.Authorization/locks@2020-05-01' = if (env == 'prod') {
  // Lock only in prod — dev/staging need to be deletable during testing
  scope: storageAccount               // applies to this specific resource
  name:  'lock-${storageAccount.name}'

  properties: {
    level: 'CanNotDelete'            // 'CanNotDelete' or 'ReadOnly'
    // 'CanNotDelete': resource can be modified but not deleted
    // 'ReadOnly':     resource cannot be modified OR deleted (use carefully — blocks deployments too)
    notes: 'Production data — requires change management approval to remove this lock'
  }
}


// =============================================================================
// 4. DIAGNOSTIC SETTINGS — send logs and metrics to Log Analytics
// =============================================================================
// Every Azure resource generates logs and metrics.  Diagnostic settings route them
// to a destination: Log Analytics workspace, Storage Account, or Event Hub.
// SRE interview question: "How do you centralise logs across all your Azure resources?"
// Answer: Diagnostic Settings → Log Analytics Workspace.

resource logAnalyticsWorkspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name:     'law-${env}-${uniqueString(resourceGroup().id)}'
  location: location
  properties: {
    sku: { name: 'PerGB2018' }   // PerGB2018 = pay per GB ingested (standard modern SKU)
    retentionInDays: 90          // 30-730 days; longer = more cost
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true   // users see only logs from resources they can access
    }
  }
}

// Diagnostic setting for the storage account (blob service)
resource storageDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name:  'diag-${storageAccount.name}'
  scope: storageAccount            // 'scope:' points to the resource being monitored

  properties: {
    workspaceId: logAnalyticsWorkspace.id   // send to our Log Analytics workspace

    // Select which log categories to enable (categories differ per resource type)
    logs: []    // storage account top-level has no logs; configure on blobService child

    // Select which metrics to collect
    metrics: [
      {
        category: 'Transaction'         // request metrics (count, latency, errors)
        enabled:  true
        retentionPolicy: { enabled: false, days: 0 }  // retention managed by workspace
      }
    ]
  }
}


// =============================================================================
// 5. PRIVATE ENDPOINT — connect to Azure services over private network
// =============================================================================
// A Private Endpoint gives a service a private IP in YOUR VNet.
// Traffic to the service stays on the Azure backbone — never hits the internet.
// Required for many enterprise compliance frameworks (PCI DSS, ISO 27001, etc.)

// Reference an existing subnet where we'll place the private endpoint
resource existingSubnet 'Microsoft.Network/virtualNetworks/subnets@2023-05-01' existing = {
  parent: sharedVnet          // parent is the existing VNet we referenced above
  name:   'snet-data'
}

resource storagePrivateEndpoint 'Microsoft.Network/privateEndpoints@2023-05-01' = {
  name:     'pep-${storageAccount.name}'
  location: location

  properties: {
    subnet: {
      id: existingSubnet.id   // which subnet to place the private IP in
    }

    privateLinkServiceConnections: [
      {
        name: 'pep-conn-${storageAccount.name}'
        properties: {
          privateLinkServiceId: storageAccount.id    // the resource to connect to
          groupIds: ['blob']
          // groupIds selects which sub-resource to expose privately:
          //   Storage: 'blob', 'file', 'queue', 'table', 'dfs'
          //   Key Vault: 'vault'
          //   SQL: 'sqlServer'
          //   Cosmos: 'Sql', 'MongoDB', etc.
        }
      }
    ]
  }
}

// Private DNS Zone — without this, DNS still resolves to the public IP
// (service won't be reachable even with a private endpoint)
resource privateDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name:     'privatelink.blob.core.windows.net'   // zone name is fixed per service type
  location: 'global'                               // Private DNS zones are always 'global'
}

// Link the DNS zone to the VNet so VMs in that VNet can resolve the private endpoint
resource dnsVnetLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent:   privateDnsZone
  name:     'link-${sharedVnet.name}'
  location: 'global'
  properties: {
    virtualNetwork:      { id: sharedVnet.id }
    registrationEnabled: false   // false = use for resolution only; true = auto-register VM names
  }
}

// Register the private endpoint in the DNS zone
resource dnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-05-01' = {
  parent: storagePrivateEndpoint
  name:   'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'config'
        properties: {
          privateDnsZoneId: privateDnsZone.id   // link to the DNS zone
        }
      }
    ]
  }
}


// =============================================================================
// 6. DEPLOYMENT SCRIPTS — run arbitrary code during deployment
// =============================================================================
// Deployment scripts let you run a PowerShell or Bash script as part of
// a Bicep deployment.  Useful for: seeding a database, generating certs,
// calling an API that has no ARM resource.

resource seedScript 'Microsoft.Resources/deploymentScripts@2023-08-01' = {
  name:     'script-seed-${env}'
  location: location
  kind:     'AzureCLI'    // 'AzureCLI' or 'AzurePowerShell'

  identity: {             // the script runs AS this identity — needs access to target resources
    type: 'UserAssigned'
    userAssignedIdentities: {}   // would reference a managed identity here
  }

  properties: {
    azCliVersion:     '2.60.0'    // pin the CLI version for reproducibility
    retentionInterval: 'PT1H'     // how long to keep the script container after completion (ISO 8601)
    timeout:           'PT10M'    // max runtime before force-kill

    scriptContent: '''
      #!/bin/bash
      # This script runs in an Azure container during deployment
      # The triple-quote ''' syntax is Bicep's raw string (no escape processing)
      echo "Seeding storage container: $STORAGE_NAME"
      az storage blob upload \
        --account-name "$STORAGE_NAME" \
        --container-name raw \
        --name seed.json \
        --data '{"seeded": true}' \
        --auth-mode login
    '''

    environmentVariables: [
      { name: 'STORAGE_NAME', value: storageAccount.name }  // pass values into the script
    ]
  }
}


// =============================================================================
// INTERVIEW Q&A SUMMARY
// =============================================================================
//
// Q: How do you make a Bicep deployment idempotent?
// A: Use deterministic resource names (uniqueString with stable seed), and
//    deterministic GUIDs for role assignments (guid() function).
//    ARM is declarative — re-running an identical template makes no changes.
//
// Q: How do you avoid storing secrets in your Bicep files?
// A: Store secrets in Key Vault.  Reference them with 'existing' + secret URI.
//    Use Key Vault References in App Service (@Microsoft.KeyVault(...)) or
//    Managed Identity + SDK DefaultAzureCredential at runtime.
//
// Q: How do you deploy the same template to dev/staging/prod with different config?
// A: Parameter files: main.dev.bicepparam, main.prod.bicepparam.
//    Or Bicep variables derived from the 'env' param with ternary/lookup maps.
//
// Q: What is 'what-if'?
// A: 'az deployment group what-if' shows what WOULD change without actually deploying.
//    Like Terraform plan.  Shows: create / modify / delete / no change for each resource.
//    Command: az deployment group what-if -g <rg> -f main.bicep -p env=prod
//
// Q: What is the difference between Bicep and ARM templates?
// A: Bicep is a DSL that compiles TO ARM JSON ('az bicep build').
//    Bicep is shorter, more readable, has type-checking, and supports modules natively.
//    The compiled ARM JSON is what Azure actually executes.  You can decompile ARM
//    back to Bicep with 'az bicep decompile'.
//
// Q: How do you handle dependencies between resources?
// A: Bicep infers dependencies automatically when you reference one resource's
//    property inside another (e.g. storageAccount.id → implicit dependency).
//    For dependencies without property references, use explicit 'dependsOn: [symbolName]'.
//
// Q: What is a Bicep parameter file?
// A: A .bicepparam file (new format) or .parameters.json file that provides
//    values for all required parameters.  Use per-environment:
//      az deployment group create -f main.bicep -p main.prod.bicepparam
//    .bicepparam syntax:  using 'main.bicep'   param env = 'prod'

// =============================================================================
// EXERCISES
// =============================================================================
// 1. Add a resource lock to the Log Analytics Workspace (lawLock) that only
//    deploys in production.  What lock level would you choose and why?
//
// 2. Use 'existing' to reference a storage account named 'saexisting1234' that
//    already exists in the SAME resource group.  Then output its primary blob endpoint.
//    Hint: existing resource + storageAccount.properties.primaryEndpoints.blob
//
// 3. THINK: What is the difference between Key Vault 'access policies' and
//    Key Vault RBAC?  Which should you use for new deployments and why?
//
//    ANSWER: Access policies are the legacy model — a flat list of object IDs with
//    specific permissions (get, list, set, delete) stored ON the vault.  They cannot
//    be scoped to individual secrets, they don't integrate with Azure AD PIM
//    (Privileged Identity Management), and they're harder to audit.
//
//    RBAC: standard Azure role model — roles are assigned at vault, secret, key, or
//    certificate scope.  Supports JIT access via PIM, full Azure Activity Log audit
//    trail, and consistent management with all other Azure resources.
//    Use RBAC (enableRbacAuthorization: true in vault properties) for all new vaults.
