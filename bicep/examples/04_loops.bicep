// =============================================================================
// 04_loops.bicep
// LOOPS in Bicep — the most powerful feature for DRY infrastructure.
// Covers: for over array, for with index, for over range(), batchSize,
//         nested loops, loop in variable, loop in output.
// Deploy: az deployment group create -g <rg> -f 04_loops.bicep
// =============================================================================

param location string = resourceGroup().location
param env      string = 'dev'

// =============================================================================
// 1. LOOP OVER AN ARRAY — create one resource per item
// =============================================================================
// Syntax:
//   resource <symbolic> '<type>@<api>' = [for <item> in <array>: {
//     ...use <item> here...
//   }]
//
// The result is an ARRAY of resources — the symbolic name refers to the whole array.

// Define a list of storage containers to create
param containerNames array = [
  'raw'
  'processed'
  'archive'
]

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name:     'sa${uniqueString(resourceGroup().id)}'
  location: location
  sku:      { name: 'Standard_LRS' }
  kind:     'StorageV2'
  properties: { supportsHttpsTrafficOnly: true, allowBlobPublicAccess: false }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-01-01' = {
  parent: storageAccount
  name:   'default'
}

// LOOP: create one container per item in containerNames
resource containers 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = [
  for name in containerNames: {       // 'name' is the loop variable — like Python: for name in containerNames
    parent: blobService               // each iteration creates a separate container under the same blobService
    name:   name                      // container name = the string from the array
    properties: { publicAccess: 'None' }
  }
]
// containers[0] = 'raw' container
// containers[1] = 'processed' container
// containers[2] = 'archive' container


// =============================================================================
// 2. LOOP WITH INDEX — access both item AND position
// =============================================================================
// Syntax:  for <item>, <index> in <array>:
// <index> is 0-based (0, 1, 2...)

param storageSkus array = [
  'Standard_LRS'
  'Standard_GRS'
  'Premium_LRS'
]

// Create multiple storage accounts, each with a unique name using the index
resource tieredStorages 'Microsoft.Storage/storageAccounts@2023-01-01' = [
  for (sku, i) in storageSkus: {       // 'sku' = value, 'i' = 0-based index
    name:     'sa${i}${uniqueString(resourceGroup().id)}'  // unique name per index
    location: location
    sku:      { name: sku }            // use the SKU from the array
    kind:     'StorageV2'
    properties: { supportsHttpsTrafficOnly: true }
    tags: {
      index: string(i)                 // string() converts int to string for tags
      sku:   sku
    }
  }
]

// Referencing items from a loop array:
output firstStorageName string = tieredStorages[0].name   // index with [n]
output lastStorageName  string = tieredStorages[length(storageSkus) - 1].name


// =============================================================================
// 3. LOOP OVER INTEGERS with range()
// =============================================================================
// range(start, count) returns [start, start+1, ..., start+count-1]
// Use when you need a known number of identical resources.

param webServerCount int = 3

// Create N public IPs for N web servers
resource publicIps 'Microsoft.Network/publicIPAddresses@2023-05-01' = [
  for i in range(0, webServerCount): {    // i = 0, 1, 2
    name:     'pip-web-${i}-${env}'       // pip-web-0-dev, pip-web-1-dev, pip-web-2-dev
    location: location
    sku:      { name: 'Standard' }        // Standard tier required for zone redundancy
    properties: {
      publicIPAllocationMethod: 'Static'  // 'Static' = IP doesn't change; 'Dynamic' = changes on stop
      dnsSettings: {
        domainNameLabel: 'web${i}${uniqueString(resourceGroup().id)}'  // must be globally unique
      }
    }
    zones: [                              // deploy across availability zones for HA
      string(i % 3 + 1)                  // cycles through '1', '2', '3' across servers
      // % is modulo: 0%3=0+1=1, 1%3=1+1=2, 2%3=2+1=3
    ]
  }
]

// Output all IP addresses as an array
output publicIpAddresses array = [
  for i in range(0, webServerCount): publicIps[i].properties.ipAddress
]


// =============================================================================
// 4. LOOP IN A VARIABLE (array comprehension)
// =============================================================================
// You can use 'for' inside a variable to build an array without deploying resources.
// Same syntax but inside a var declaration.

param environments array = ['dev', 'staging', 'prod']

// Build an array of resource group names
var rgNames = [
  for e in environments: 'rg-myapp-${e}'   // ['rg-myapp-dev', 'rg-myapp-staging', 'rg-myapp-prod']
]

// Build an array of tag objects — one per environment
var envTags = [
  for (e, i) in environments: {            // each item is an object
    environment: e
    index:       i
    isProd:      e == 'prod'
  }
]

output computedRgNames array = rgNames
output computedEnvTags  array = envTags


// =============================================================================
// 5. LOOP IN OUTPUT
// =============================================================================
// You can 'for' directly inside an output to project an array from resources.

// Collect all container names after deployment
output containerIds array = [
  for i in range(0, length(containerNames)): containers[i].id
  // containers[i] references the i-th resource in the loop at the top of the file
]

// Collect storage account names into a flat array
output tieredStorageNames array = [
  for i in range(0, length(storageSkus)): tieredStorages[i].name
]


// =============================================================================
// 6. LOOP OVER ARRAY OF OBJECTS (most realistic pattern)
// =============================================================================
// Real infrastructure lists are objects with multiple fields, not just strings.

param subnets array = [
  { name: 'snet-web',  prefix: '10.0.1.0/24', delegated: false }
  { name: 'snet-app',  prefix: '10.0.2.0/24', delegated: true  }
  { name: 'snet-data', prefix: '10.0.3.0/24', delegated: false }
]

// Loop over objects — access fields with .fieldName inside the loop
var subnetConfigs = [
  for subnet in subnets: {         // 'subnet' is the current object from the array
    name: subnet.name              // access fields with dot notation
    properties: {
      addressPrefix:  subnet.prefix
      // Conditional inside a loop — shown fully in 05_conditions.bicep
      delegations: subnet.delegated ? [
        { name: 'appservice', properties: { serviceName: 'Microsoft.Web/serverFarms' } }
      ] : []
    }
  }
]
// subnetConfigs is now an array of ARM subnet objects — useful for the VNet inline property


// =============================================================================
// 7. @batchSize — controlling parallelism
// =============================================================================
// By default Bicep deploys all loop iterations IN PARALLEL (maximum speed).
// Some resources have constraints that require sequential deployment.
// @batchSize(n) limits to n concurrent deployments at a time.

@batchSize(1)   // deploy ONE at a time (fully sequential) — use for DB migrations, etc.
resource sequentialStorage 'Microsoft.Storage/storageAccounts@2023-01-01' = [
  for i in range(0, 3): {
    name:     'seq${i}${uniqueString(resourceGroup().id)}'
    location: location
    sku:      { name: 'Standard_LRS' }
    kind:     'StorageV2'
    properties: { supportsHttpsTrafficOnly: true }
    // These three accounts deploy one after the other, not at the same time
    // Use @batchSize(2) for "at most 2 at a time"
  }
]


// =============================================================================
// EXERCISES
// =============================================================================
// 1. Create a loop that deploys one NSG per subnet in the 'subnets' array above.
//    Name each NSG 'nsg-<subnet.name>'.
//    Hint: use 'for subnet in subnets: { name: ..., ... }'
//
// 2. Add a loop output 'subnetPrefixes' that collects all the prefix strings
//    from the 'subnets' param into an array.
//    Expected: ['10.0.1.0/24', '10.0.2.0/24', '10.0.3.0/24']
//    Hint: use a loop in output or a var comprehension.
//
// 3. What happens if you add @batchSize(1) to the 'containers' resource loop?
//    When would you NEED that for containers?  (Think: if a script runs on each
//    container after creation and the script depends on the previous container's data.)
