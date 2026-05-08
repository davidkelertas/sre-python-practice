// =============================================================================
// 06_modules.bicep
// Modules — splitting large templates into reusable pieces.
// Covers: module syntax, passing params, consuming outputs, scope, registry.
// =============================================================================
// STRUCTURE FOR THIS DEMO:
//   06_modules.bicep           ← this file (orchestrator / "main" template)
//   modules/storage.bicep      ← storage account module
//   modules/networking.bicep   ← VNet + subnets module
//
// In a real project you might have:
//   main.bicep
//   modules/
//     storage.bicep
//     aks.bicep
//     keyvault.bicep
//     monitoring.bicep
// =============================================================================

// Scope for THIS file (the orchestrator) — resource group by default
targetScope = 'resourceGroup'

param location  string = resourceGroup().location
param env       string = 'dev'
param appName   string = 'myapp'


// =============================================================================
// MODULE SYNTAX
// =============================================================================
// Syntax:
//   module <symbolicName> '<path-or-registry-reference>' = {
//     name: '<deployment name>'   // shown in Azure portal deployment history
//     scope: <scope>              // optional — defaults to same scope as caller
//     params: {
//       paramName: value
//     }
//   }
//
// <path> can be:
//   './modules/storage.bicep'          relative path to a local file
//   'br/public:avm/res/storage/...'   Azure Verified Modules (public registry)
//   'br:<registry>.azurecr.io/...'   your own private registry
//
// When Bicep compiles, it inlines the module into the ARM template as a
// nested deployment.  Each module gets its own deployment scope and history entry.


// --- Module 1: Storage ---
module storage './modules/storage.bicep' = {
  name: 'storage-deployment'          // name appears in Azure portal deployment list
  params: {                           // pass values to the module's 'param' declarations
    location: location
    env:      env
    appName:  appName
  }
  // 'scope' not specified → inherits this file's scope (same resource group)
}

// --- Module 2: Networking ---
module networking './modules/networking.bicep' = {
  name: 'networking-deployment'
  params: {
    location:          location
    env:               env
    vnetAddressPrefix: '10.0.0.0/16'
  }
}


// =============================================================================
// CONSUMING MODULE OUTPUTS
// =============================================================================
// After a module deploys, you access its outputs via:
//   <symbolicName>.outputs.<outputName>
// Bicep automatically makes the calling module wait for the module to finish
// before anything that references its outputs can proceed.

var storageAccountId   = storage.outputs.storageAccountId    // string
var storageAccountName = storage.outputs.storageAccountName  // string
var webSubnetId        = networking.outputs.webSubnetId      // string

// This creates an IMPLICIT DEPENDENCY: any resource here that references
// storage.outputs or networking.outputs will wait for those modules to complete.


// =============================================================================
// CHAINING MODULES — passing one module's output into another
// =============================================================================
// A third module that needs both the storage account AND the subnet ID:

module appService './modules/appservice.bicep' = {
  name: 'appservice-deployment'
  params: {
    location:           location
    env:                env
    storageAccountName: storage.outputs.storageAccountName   // from module 1
    subnetId:           networking.outputs.webSubnetId       // from module 2
    // Bicep infers: deploy 'storage' and 'networking' before 'appService'
  }
}


// =============================================================================
// EXPLICIT dependsOn — when there's no output reference
// =============================================================================
// Sometimes a module depends on another but doesn't use its outputs.
// Use 'dependsOn' to force ordering.

module monitoring './modules/monitoring.bicep' = {
  name: 'monitoring-deployment'
  params: {
    location:          location
    targetResourceIds: [storageAccountId]   // already creates a dependency via output reference
  }
  dependsOn: [
    networking    // also wait for networking even though we don't use its outputs here
    // This ensures the VNet diagnostics are in place before monitoring tries to connect
  ]
}


// =============================================================================
// MODULE SCOPE — deploying to a different scope than the caller
// =============================================================================
// Use 'scope:' to deploy a module to a different scope.
// Example: the main template is at resource group scope but one module
// creates a resource at subscription scope (e.g., a Policy Assignment).

// module policyAssignment './modules/policy.bicep' = {
//   name:  'policy-deployment'
//   scope: subscription()    // deploy THIS module to subscription scope
//   params: {
//     policyDefinitionId: '/providers/Microsoft.Authorization/policyDefinitions/xxx'
//   }
// }

// Other scope examples:
//   scope: resourceGroup('other-rg')         deploy into a different RG in same sub
//   scope: resourceGroup(subId, 'other-rg')  deploy into a different sub + RG
//   scope: managementGroup('mg-id')          management group scope


// =============================================================================
// LOOP OVER MODULES — deploy the same module multiple times
// =============================================================================
// Just like resources, modules support 'for' loops.

param secondaryRegions array = ['australiasoutheast', 'southeastasia']

module storageReplicas './modules/storage.bicep' = [
  for region in secondaryRegions: {    // one module deployment per region
    name:   'storage-${region}'        // unique deployment name per iteration
    params: {
      location: region                 // deploy to each region in turn
      env:      env
      appName:  appName
    }
  }
]

// Access outputs from a looped module:
output replicaNames array = [
  for i in range(0, length(secondaryRegions)): storageReplicas[i].outputs.storageAccountName
]


// =============================================================================
// AZURE VERIFIED MODULES (AVM) — Microsoft's official module registry
// =============================================================================
// Instead of writing modules from scratch, you can use pre-built, tested modules.
// Browse at: https://azure.github.io/Azure-Verified-Modules/
//
// Example using AVM storage module from the public registry:
//
// module storageAvm 'br/public:avm/res/storage/storage-account:0.9.1' = {
//   name: 'storage-avm'
//   params: {
//     name:     'sa${uniqueString(resourceGroup().id)}'
//     location: location
//     skuName:  'Standard_LRS'
//   }
// }
//
// To use public registry, add to bicepconfig.json:
// {
//   "moduleAliases": {
//     "br": {
//       "public": {
//         "registry": "mcr.microsoft.com",
//         "modulePath": "bicep/modules"
//       }
//     }
//   }
// }


// =============================================================================
// OUTPUTS FROM THE ORCHESTRATOR
// =============================================================================

output storageId        string = storage.outputs.storageAccountId
output storageAccountName string = storage.outputs.storageAccountName
output vnetId           string = networking.outputs.vnetId
output webSubnetId      string = networking.outputs.webSubnetId


// =============================================================================
// SAMPLE MODULE FILE: modules/storage.bicep (what it looks like inside)
// =============================================================================
// (Not runnable here — shown as inline documentation)
//
// param location string
// param env      string
// param appName  string
//
// var saName = 'sa${toLower(appName)}${uniqueString(resourceGroup().id)}'
//
// resource sa 'Microsoft.Storage/storageAccounts@2023-01-01' = {
//   name:     saName
//   location: location
//   sku:      { name: 'Standard_LRS' }
//   kind:     'StorageV2'
//   properties: { supportsHttpsTrafficOnly: true }
//   tags:     { environment: env }
// }
//
// output storageAccountId   string = sa.id
// output storageAccountName string = sa.name


// =============================================================================
// EXERCISES
// =============================================================================
// 1. Write a module file 'modules/keyvault.bicep' that:
//    - Takes params: location, env, objectId (string)
//    - Deploys a Key Vault with standard SKU
//    - Outputs: keyVaultId, keyVaultUri
//    Then add a 'module keyVault' block here that calls it.
//
// 2. The 'storageReplicas' loop deploys to secondary regions.
//    Add an output 'replicaStorageIds' (array) that collects the .id of each replica.
//    Hint: same pattern as 'replicaNames' but with .storageAccountId instead of .storageAccountName
//
// 3. THINK: What are two advantages of using modules over one giant Bicep file?
//    And what is one disadvantage?
//
//    Advantages:
//      - Reusability: a storage module can be called from many orchestrators.
//      - Separation of concerns: networking team owns networking.bicep; app team owns main.
//    Disadvantage:
//      - Harder to debug: errors surface in the nested deployment, not the main template.
//        You must drill into the child deployment in the portal to find the root cause.
