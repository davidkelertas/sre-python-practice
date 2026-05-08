// =============================================================================
// 07_rbac_and_identity.bicep
// Role-Based Access Control (RBAC) and Managed Identity — SRE essentials.
// Covers: role assignments, built-in role IDs, managed identity, principalId.
// Deploy: az deployment group create -g <rg> -f 07_rbac_and_identity.bicep
// =============================================================================

param location string = resourceGroup().location
param env      string = 'dev'


// =============================================================================
// MANAGED IDENTITY
// =============================================================================
// A Managed Identity is an Azure AD identity automatically managed by Azure.
// Your app or service authenticates AS this identity — no passwords or secrets needed.
//
// Two types:
//   System-assigned: tied to one resource; deleted when resource is deleted.
//   User-assigned:   standalone resource; can be shared across multiple resources.
//
// WHY it matters for SRE:
//   Without managed identity: store a service principal secret in a Key Vault (or worse, in code).
//   With managed identity:    the VM/AKS/App Service gets an identity token automatically.
//   The app calls Azure AD, gets a token, calls the API.  No secret to rotate or leak.

// --- User-Assigned Managed Identity ---
resource managedIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name:     'id-${env}-app'
  location: location
  tags:     { environment: env }
  // No 'properties' needed — the identity is created with defaults
}

// After creation, you use:
//   managedIdentity.properties.principalId  — the Object ID in Azure AD (used in role assignments)
//   managedIdentity.properties.clientId     — the App ID (used in SDK authentication)
//   managedIdentity.id                      — the ARM resource ID (used in resource identity blocks)


// =============================================================================
// ROLE ASSIGNMENT
// =============================================================================
// A Role Assignment = WHO + WHAT ROLE + WHERE (scope)
// Resource type: Microsoft.Authorization/roleAssignments
// Scope: resource group, subscription, management group, or specific resource
//
// BUILT-IN ROLE IDs — memorise the common ones for interviews:
//   Owner:                    '8e3af657-a8ff-443c-a75c-2fe8c4bcb635'   (all perms + assign roles)
//   Contributor:              'b24988ac-6180-42a0-ab88-20f7382dd24c'   (manage resources, not RBAC)
//   Reader:                   'acdd72a7-3385-48ef-bd42-f606fba81ae7'   (read-only)
//   Storage Blob Data Owner:  'b7e6dc6d-f1e8-4753-8033-0f276bb0955b'
//   Storage Blob Data Contributor: 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
//   Storage Blob Data Reader: '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1'
//   Key Vault Secrets Officer:'b86a8fe4-44ce-4948-aee5-eccb2c155cd7'
//   Key Vault Secrets User:   '4633458b-17de-408a-b874-0445c86b69e6'
//   Key Vault Reader:         '21090545-7ca7-4776-b22c-e363652d74d4'
//   Monitoring Reader:        '43d0d8ad-25c7-4714-9337-8ba259a9fe05'
//   AcrPull:                  '7f951dda-4ed3-4680-a7ca-43fe172d538d'  (pull from Container Registry)
//
// Find any role ID with:
//   az role definition list --name "Storage Blob Data Reader" --query "[0].name"

// Declare role IDs as variables — easier to read than raw GUIDs
var storageContributorRoleId = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'  // Storage Blob Data Contributor
var keyVaultSecretsUserId    = '4633458b-17de-408a-b874-0445c86b69e6'  // Key Vault Secrets User


// --- Storage Account for the identity to access ---
resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name:     'sa${uniqueString(resourceGroup().id)}'
  location: location
  sku:      { name: 'Standard_LRS' }
  kind:     'StorageV2'
  properties: { supportsHttpsTrafficOnly: true }
}


// --- Role Assignment: give the managed identity access to Storage ---
// Role assignment names MUST be GUIDs — use guid() to generate a stable one
// from deterministic inputs so re-deployments don't create duplicates.

resource storageBlobRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  // Scope: this assignment applies to 'storageAccount' specifically.
  // Put the resource inside the parent scope using 'scope:'.
  scope: storageAccount           // assignment scoped to THIS storage account only

  // Name must be a GUID — generate it deterministically so it's idempotent
  name: guid(storageAccount.id, managedIdentity.properties.principalId, storageContributorRoleId)
  // guid(seed1, seed2, ...) — deterministic GUID from inputs
  // Same inputs → same GUID → same role assignment → no duplicate on re-deploy

  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      storageContributorRoleId     // GUID of the built-in role
    )
    // subscriptionResourceId builds:
    //   /subscriptions/<subId>/providers/Microsoft.Authorization/roleDefinitions/<roleId>

    principalId:   managedIdentity.properties.principalId   // WHO gets the role
    principalType: 'ServicePrincipal'
    // principalType speeds up propagation and prevents timing bugs:
    //   'User'             — Azure AD user
    //   'Group'            — Azure AD group
    //   'ServicePrincipal' — service principal or managed identity
    //   'ForeignGroup'     — guest / external user group
  }
}


// --- Resource Group scope role assignment ---
// To grant access to the WHOLE resource group instead of one resource:
// Remove 'scope:' → defaults to the resource group this file targets.

resource rgReaderRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  // No 'scope:' → this assignment applies to the RESOURCE GROUP
  name: guid(resourceGroup().id, managedIdentity.properties.principalId, '43d0d8ad-25c7-4714-9337-8ba259a9fe05')
  // Using Monitoring Reader GUID inline instead of a var (both approaches are valid)

  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '43d0d8ad-25c7-4714-9337-8ba259a9fe05'   // Monitoring Reader
    )
    principalId:   managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}


// =============================================================================
// ASSIGNING A MANAGED IDENTITY TO A RESOURCE
// =============================================================================
// Resources that can USE a managed identity (e.g. VMs, App Services, AKS nodes)
// declare it in their 'identity' block.

// Example: App Service Plan + Web App with the user-assigned identity attached
resource appServicePlan 'Microsoft.Web/serverfarms@2023-01-01' = {
  name:     'asp-${env}'
  location: location
  sku:      { name: 'B1', tier: 'Basic' }
  kind:     'linux'
  properties: { reserved: true }   // reserved: true = Linux
}

resource webApp 'Microsoft.Web/sites@2023-01-01' = {
  name:     'app-${uniqueString(resourceGroup().id)}-${env}'
  location: location

  // IDENTITY BLOCK — tells Azure which identities this resource uses
  identity: {
    type: 'UserAssigned'                  // 'SystemAssigned', 'UserAssigned', or 'SystemAssigned, UserAssigned'
    userAssignedIdentities: {
      '${managedIdentity.id}': {}         // the value is always {} (empty object)
      // The KEY is the managed identity's ARM resource ID
      // Azure reads this and injects the identity's token endpoint into the app runtime
    }
  }

  properties: {
    serverFarmId: appServicePlan.id
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.12'
      appSettings: [
        // Tell the app WHICH managed identity to use when multiple are attached
        { name: 'AZURE_CLIENT_ID', value: managedIdentity.properties.clientId }
        // Azure SDK DefaultAzureCredential automatically picks this up
        // No password, no secret — just the client ID of the identity to use
        { name: 'STORAGE_ACCOUNT', value: storageAccount.name }
      ]
    }
  }
}


// =============================================================================
// SYSTEM-ASSIGNED IDENTITY (simpler, less flexible)
// =============================================================================
// No separate resource needed — just add identity to the resource itself.

resource funcApp 'Microsoft.Web/sites@2023-01-01' = {
  name:     'func-${uniqueString(resourceGroup().id)}'
  location: location
  kind:     'functionapp,linux'

  identity: {
    type: 'SystemAssigned'    // Azure creates and manages the identity automatically
    // No userAssignedIdentities block needed
  }

  properties: {
    serverFarmId: appServicePlan.id
    siteConfig: { linuxFxVersion: 'PYTHON|3.12' }
  }
}

// After deployment, funcApp.identity.principalId is the system identity's Object ID.
// Use it in role assignments exactly like the user-assigned identity's principalId.

resource funcStorageRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storageAccount
  name:  guid(storageAccount.id, funcApp.identity.principalId, storageContributorRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageContributorRoleId)
    principalId:   funcApp.identity.principalId   // system-assigned identity's principal ID
    principalType: 'ServicePrincipal'
  }
}


// =============================================================================
// OUTPUTS
// =============================================================================

output managedIdentityId          string = managedIdentity.id
output managedIdentityPrincipalId string = managedIdentity.properties.principalId
output managedIdentityClientId    string = managedIdentity.properties.clientId
output webAppName                 string = webApp.name
output storageAccountName         string = storageAccount.name


// =============================================================================
// EXERCISES
// =============================================================================
// 1. Add a Key Vault resource and give the managed identity the 'Key Vault Secrets User'
//    role on it so the web app can read secrets at runtime.
//    Hint: use keyVaultSecretsUserId which is already declared as a variable above.
//    The role assignment 'scope:' should point to the key vault resource.
//
// 2. THINK: Why use a GUID derived from guid(resource.id, principalId, roleId)
//    as the role assignment name?  What goes wrong if you use a hardcoded GUID?
//    What goes wrong if you use newGuid()?
//
//    ANSWER: guid() is deterministic — same inputs always produce the same GUID.
//    This makes role assignments idempotent: re-deploying doesn't create a duplicate.
//    Hardcoded GUID: fine for one deployment target, breaks if you deploy the same
//    template to multiple resource groups (duplicate GUID = ARM error).
//    newGuid(): generates a different GUID every deployment — creates a NEW role
//    assignment each time, leaving orphaned assignments that accumulate over time.
//
// 3. THINK: What is the difference between system-assigned and user-assigned identity?
//    When would you choose each?
//
//    System-assigned: lifecycle tied to the resource — auto-deleted when resource is
//    deleted.  Simpler but can't be shared.  Good for resources with unique access needs.
//
//    User-assigned: separate ARM resource — survives the compute resource's deletion.
//    Can be attached to multiple resources simultaneously.  Good when multiple resources
//    (e.g., 5 web apps) need the same permissions — assign role once to the identity,
//    attach identity to all 5 resources.  Also good for pre-provisioning identity before
//    the compute resource exists (eliminates the "chicken and egg" timing problem).
