// =============================================================================
// 01_parameters_variables_outputs.bicep
// The building blocks of every Bicep file.
// Deploy: az deployment group create -g <rg> -f 01_parameters_variables_outputs.bicep -p env=prod
// =============================================================================

// --- targetScope ---
// Tells Bicep WHERE this template deploys to.
// Options: 'resourceGroup' (default), 'subscription', 'managementGroup', 'tenant'
// You only need to write this line when you CHANGE from the default.
targetScope = 'resourceGroup'   // default — most templates deploy here


// =============================================================================
// PARAMETERS — values the caller passes IN when deploying
// =============================================================================
// 'param' declares a parameter.  The caller supplies the value via:
//   -p env=prod                    (CLI)
//   parameters: { env: 'prod' }   (Bicep module call)
//   A parameters file (.bicepparam or .parameters.json)

param env string                  // required — no default, caller MUST provide it

// --- Decorators — @word() lines sit directly above the param they describe ---
// Decorators validate input, document the param, and appear in the ARM schema.

@description('Short name of the application — used in resource names.')
@minLength(2)                     // reject strings shorter than 2 characters
@maxLength(10)                    // reject strings longer than 10 characters
param appName string = 'myapp'    // optional — has a default value of 'myapp'

@description('Azure region to deploy into.')
param location string = resourceGroup().location
// resourceGroup().location reads the location of the RG this deploys into.
// This is the most common default — avoids hard-coding a region.

@description('SKU tier for resources.')
@allowed([                        // only accept values in this list; anything else = error at deploy time
  'Basic'
  'Standard'
  'Premium'
])
param skuTier string = 'Standard'

@description('Number of instances (1-10).')
@minValue(1)                      // reject integers below 1
@maxValue(10)                     // reject integers above 10
param instanceCount int = 2

@description('Enable diagnostic logging.')
param enableDiagnostics bool = false   // bool params are true or false

@description('Tags to apply to all resources.')
param tags object = {             // object param — key/value pairs
  project: 'sre-demo'
  owner:   'david'
}

@description('Database password — stored securely, never logged.')
@secure()                         // @secure() = Bicep never logs or displays this value
param dbPassword string = newGuid()   // newGuid() generates a random GUID as default


// =============================================================================
// VARIABLES — computed values used inside this file only
// =============================================================================
// 'var' declares a variable.  Unlike params, variables cannot be set by the caller.
// Use vars to avoid repeating the same expression in multiple places.

var prefix = toLower('${appName}-${env}')
// toLower() converts to lowercase — Azure resource names are case-insensitive
// '${expression}' is Bicep string interpolation (like Python f-strings)
// result: 'myapp-prod'

var storageAccountName = '${prefix}sa${uniqueString(resourceGroup().id)}'
// uniqueString() generates a deterministic 13-char hash from its input.
// resourceGroup().id is unique per resource group, so this gives a stable,
// unique-enough name for the storage account (must be globally unique).
// result: 'myapp-prodsa<hash>' — but WAIT: storage names must be letters+digits only.
// Fix below:

var safeStorageName = replace(replace(storageAccountName, '-', ''), '_', '')
// replace(string, old, new) removes characters not allowed in storage account names.
// Chained: first removes '-', then removes '_'.

var isProduction = env == 'prod'   // bool expression — true when env is 'prod'

var commonTags = union(tags, {     // union() merges two objects (right wins on conflict)
  environment: env
  deployedAt:  utcNow('yyyy-MM-dd')   // utcNow() returns current UTC time in given format
  managedBy:   'bicep'
})
// commonTags now has everything from the 'tags' param PLUS the three fields above.

var skuMap = {                     // object used as a lookup table (like a Python dict)
  Basic:    { name: 'B1',  tier: 'Basic' }
  Standard: { name: 'S1',  tier: 'Standard' }
  Premium:  { name: 'P1v3', tier: 'PremiumV3' }
}
var selectedSku = skuMap[skuTier]  // index into the object with a dynamic key
// If skuTier = 'Standard', selectedSku = { name: 'S1', tier: 'Standard' }


// =============================================================================
// OUTPUTS — values this template sends BACK to the caller
// =============================================================================
// 'output' exposes values after deployment.
// Other templates can reference these via module outputs (see 06_modules.bicep).
// The Azure Portal and CLI display them after a successful deployment.

output resolvedPrefix string = prefix
// Shows the caller what prefix was computed — useful for debugging

output storageAccountName string = safeStorageName
// Other templates can feed this name into a resource reference

output isProduction bool = isProduction

output skuDetails object = selectedSku
// Outputs can be any type: string, int, bool, object, array

@description('Resource group location used by this deployment.')
output deploymentLocation string = location   // decorators work on outputs too

@secure()                                      // @secure() on output — never log/display it
output generatedPassword string = dbPassword   // pass a secret back without exposing it in logs


// =============================================================================
// KEY FUNCTIONS CHEAT SHEET
// =============================================================================
// String functions:
//   toLower(s)          lowercase
//   toUpper(s)          uppercase
//   replace(s,old,new)  find & replace
//   concat(a,b,c)       join strings (prefer interpolation '${a}${b}' instead)
//   contains(s,sub)     returns bool — true if sub is in s
//   startsWith(s,pre)   true if s starts with pre
//   endsWith(s,suf)     true if s ends with suf
//   substring(s,i,n)    n chars starting at index i
//   split(s,sep)        string → array on separator
//   trim(s)             remove leading/trailing whitespace
//   length(s)           number of characters
//
// Resource/scope functions:
//   resourceGroup()     object with .id .name .location .tags
//   subscription()      object with .id .subscriptionId .tenantId
//   uniqueString(seed)  13-char deterministic hash — great for globally-unique names
//   newGuid()           random UUID — use for secrets, NOT resource names (not stable)
//   utcNow(format)      current UTC datetime string
//
// Object/array functions:
//   union(a,b)          merge objects; or concat arrays
//   intersection(a,b)   keys/items present in BOTH
//   contains(obj,key)   true if obj has the key
//   empty(val)          true if string/array/object is empty
//   length(arr)         number of items in array
//   first(arr)          first item
//   last(arr)           last item
//   range(start,count)  array of ints [start .. start+count-1]
//   flatten(arr)        convert array-of-arrays to flat array
