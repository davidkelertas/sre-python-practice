// =============================================================================
// 05_conditions.bicep
// Conditional resources, inline ternary, null-coalescing, and if() patterns.
// Covers: resource = if(), ? : ternary, ?? null-coalescing, conditional properties.
// Deploy: az deployment group create -g <rg> -f 05_conditions.bicep -p env=prod
// =============================================================================

param location string = resourceGroup().location
param env      string = 'dev'     // 'dev', 'staging', or 'prod'

// Derive booleans from the environment — used throughout the file
var isProd    = env == 'prod'     // true only in production
var isNotProd = !isProd           // ! = logical NOT — flips the boolean


// =============================================================================
// 1. CONDITIONAL RESOURCE — deploy only when a condition is true
// =============================================================================
// Syntax:  resource <name> '<type>@<api>' = if (<condition>) { ... }
// When condition is false: the resource is skipped entirely (not deployed, not deleted).
// When condition is true:  normal deployment.

// Deploy a DDoS Protection Plan only in prod (it costs ~$2,700/month — don't want it in dev!)
resource ddosProtectionPlan 'Microsoft.Network/ddosProtectionPlans@2023-05-01' = if (isProd) {
  // This whole block is skipped when isProd == false
  name:     'ddos-${env}'
  location: location
  properties: {}  // DDoS plan has no configurable properties in ARM
}

// Deploy a Basic Load Balancer in dev, Standard in prod
// (Two separate resources with complementary conditions — only one will deploy)
resource lbDev 'Microsoft.Network/loadBalancers@2023-05-01' = if (isNotProd) {
  name:     'lb-${env}'
  location: location
  sku: { name: 'Basic', tier: 'Regional' }     // Basic LB — free tier, no SLA
  properties: { frontendIPConfigurations: [] }
}

resource lbProd 'Microsoft.Network/loadBalancers@2023-05-01' = if (isProd) {
  name:     'lb-${env}'
  location: location
  sku: { name: 'Standard', tier: 'Regional' }  // Standard LB — zone-redundant, has SLA
  properties: { frontendIPConfigurations: [] }
}


// =============================================================================
// 2. REFERENCING A CONDITIONAL RESOURCE
// =============================================================================
// If a conditional resource is not deployed, its symbolic name is null.
// You CANNOT safely reference its properties unless you guard with the same condition.

// SAFE: guard the reference with the same condition
var lbId = isProd ? lbProd.id : lbDev.id
// ? : is the TERNARY operator:  condition ? valueIfTrue : valueIfFalse
// If isProd = true:  lbId = lbProd.id
// If isProd = false: lbId = lbDev.id

// UNSAFE (would cause an error at deploy time in non-prod):
// var lbId = lbProd.id   ← lbProd might not exist, so .id would fail

// REFERENCING DDOS (only in prod):
// Other templates that reference ddosProtectionPlan should also be conditional.


// =============================================================================
// 3. TERNARY OPERATOR — inline if/else for values
// =============================================================================
// Syntax:  condition ? valueIfTrue : valueIfFalse
// Use inside property values, variable declarations, and outputs.

var storageSkuName  = isProd ? 'Standard_GRS' : 'Standard_LRS'
// Geo-redundant in prod (survives a regional outage), locally redundant in dev (cheaper)

var replicaCount    = isProd ? 3 : 1
// 3 replicas in prod for HA; 1 in dev to save cost

var deletionLockEnabled = env == 'prod'   // bool: only lock prod resources
// Resource locks prevent accidental deletion — critical for prod databases

// Ternary in resource properties — inline, no 'if()' block needed
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name:     'kv-${uniqueString(resourceGroup().id)}'
  location: location

  properties: {
    sku: {
      family: 'A'
      name:   isProd ? 'premium' : 'standard'   // inline ternary in property value
      // 'premium' supports HSM-backed keys (hardware security module)
      // 'standard' is software-backed — fine for dev/staging
    }

    tenantId: subscription().tenantId    // subscription() function returns Azure AD tenant

    enableSoftDelete:         true       // keeps secrets for 90 days after deletion
    softDeleteRetentionInDays: isProd ? 90 : 7  // shorter retention in dev saves cost
    enablePurgeProtection:    isProd     // bool — prevent hard deletion in prod only

    // Access policies control who can read/write secrets
    // (In modern setups, prefer RBAC over access policies — see 07_rbac.bicep)
    accessPolicies: []

    networkAcls: {
      bypass:        'AzureServices'
      defaultAction: isProd ? 'Deny' : 'Allow'   // lockdown network in prod; open in dev
    }
  }
}


// =============================================================================
// 4. NULL COALESCING (??) — provide a fallback for null/undefined values
// =============================================================================
// Syntax:  expression ?? fallback
// If 'expression' evaluates to null, use 'fallback' instead.
// This is new in Bicep — very useful with optional parameters.

@description('Custom DNS prefix — leave empty to use the default.')
param customDnsPrefix string = ''   // empty string by default (user can override)

var dnsPrefix = !empty(customDnsPrefix) ? customDnsPrefix : 'app-${uniqueString(resourceGroup().id)}'
// empty() returns true for empty string/array/object
// If customDnsPrefix is not empty: use it; otherwise: generate a default
// This is the pattern to use instead of ?? for string emptiness checks


// =============================================================================
// 5. CONDITIONAL INSIDE A LOOP
// =============================================================================
// You can combine conditions and loops (but cannot use 'if()' on loop resources directly).
// Use ternary inside loop body properties instead.

param envList array = ['dev', 'staging', 'prod']

resource envStorages 'Microsoft.Storage/storageAccounts@2023-01-01' = [
  for e in envList: {
    name:     'sa${e}${uniqueString(resourceGroup().id)}'
    location: location
    sku:      { name: e == 'prod' ? 'Standard_GRS' : 'Standard_LRS' }  // ternary per item
    kind:     'StorageV2'
    properties: {
      supportsHttpsTrafficOnly: true
      allowBlobPublicAccess:    false
      minimumTlsVersion:        e == 'prod' ? 'TLS1_2' : 'TLS1_0'     // stricter in prod
    }
    tags: { environment: e, isProd: string(e == 'prod') }
  }
]
// Note: 'if()' on a looped resource is not supported directly.
// To conditionally skip a subset of items, filter the array before the loop:
var prodOnly = filter(envList, e => e == 'prod')   // filter() keeps items matching the condition
// Then loop over prodOnly instead of envList.


// =============================================================================
// 6. CONDITIONAL PROPERTY (include/exclude based on condition)
// =============================================================================
// Sometimes you want a property only when a condition is met.
// Use 'null' to omit a property — ARM ignores null values.

var diagnosticSettings = isProd ? {
  workspaceId:    '/subscriptions/xxx/resourceGroups/yyy/providers/Microsoft.OperationalInsights/workspaces/law'
  retentionDays:  90
} : null    // null means: don't include diagnostic settings in dev

// In a resource, you'd reference this as:
// diagnosticWorkspaceId: diagnosticSettings != null ? diagnosticSettings.workspaceId : null


// =============================================================================
// OUTPUTS
// =============================================================================

output deployedLbId string = lbId
output keyVaultName string = keyVault.name
output dnsPrefix    string = dnsPrefix
output isProd       bool   = isProd

// Conditional output — only meaningful in prod
output ddosPlanId string = isProd ? ddosProtectionPlan.id : 'not-deployed'
// Important: even in the false branch we must provide a value of the right type (string).
// You cannot have a null output — use a placeholder string like 'not-deployed'.


// =============================================================================
// EXERCISES
// =============================================================================
// 1. Add a parameter 'enablePrivateEndpoints' (bool, default false).
//    Deploy a private endpoint resource only when enablePrivateEndpoints == true.
//    (You don't need to make it functional — just show the conditional structure.)
//
// resource privateEndpoint '...' = if (enablePrivateEndpoints) { ... }
//
// 2. Change the Key Vault's softDeleteRetentionInDays to use a parameter instead
//    of a hardcoded ternary.  Add a param 'retentionDays' (int, default 7, max 90).
//    Only enforce minimum 30 days when isProd == true.
//    Hint:  isProd ? max(30, retentionDays) : retentionDays
//    (max() returns the larger of two numbers)
//
// 3. THINK: What is the difference between these two approaches?
//      A) resource foo '...' = if (condition) { ... }      (conditional resource)
//      B) sku: { name: condition ? 'Premium' : 'Standard' } (ternary in property)
//    When would you choose A vs B?
//
//    ANSWER: A deploys/skips the ENTIRE resource — the resource either exists or not.
//    B always deploys the resource but changes ONE property based on the condition.
//    Use A when the resource itself is environment-specific (cost, compliance).
//    Use B when the resource is always needed but its config differs by environment.
