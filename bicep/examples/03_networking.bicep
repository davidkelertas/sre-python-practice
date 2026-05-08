// =============================================================================
// 03_networking.bicep
// Virtual Network + Subnets — parent/child resources, address spaces, NSGs.
// Covers: nested child syntax, dependsOn, resource references.
// Deploy: az deployment group create -g <rg> -f 03_networking.bicep
// =============================================================================

param location string = resourceGroup().location
param env      string = 'dev'

// Address space for the whole VNet — must not overlap with on-prem or other VNets
param vnetAddressPrefix string = '10.0.0.0/16'
// /16 = 65,536 addresses.  Subnets must be subsets of this range.

// Individual subnet CIDRs — each subnet is carved out of the VNet prefix
param webSubnetPrefix  string = '10.0.1.0/24'   // 256 addresses for web tier
param appSubnetPrefix  string = '10.0.2.0/24'   // 256 addresses for app tier
param dataSubnetPrefix string = '10.0.3.0/24'   // 256 addresses for data tier

var vnetName = 'vnet-${env}-eastus'   // naming convention: type-env-region


// =============================================================================
// NETWORK SECURITY GROUP (NSG)
// =============================================================================
// An NSG is a stateful firewall attached to a subnet or NIC.
// Rules are evaluated by priority (lower number = higher priority).
// Each rule: allow or deny a protocol/port from a source to a destination.

resource webNsg 'Microsoft.Network/networkSecurityGroups@2023-05-01' = {
  name:     'nsg-web-${env}'
  location: location
  tags:     { environment: env }

  properties: {
    securityRules: [              // array of rules; evaluated in priority order

      {
        name: 'AllowHttpsInbound'
        properties: {
          priority:             100          // 100–4096; lower = checked first
          direction:            'Inbound'    // 'Inbound' or 'Outbound'
          access:               'Allow'      // 'Allow' or 'Deny'
          protocol:             'Tcp'        // 'Tcp', 'Udp', 'Icmp', '*' (all)
          sourceAddressPrefix:  'Internet'   // special tag: all internet traffic
          sourcePortRange:      '*'          // any source port
          destinationAddressPrefix: '*'      // any destination IP in the subnet
          destinationPortRange: '443'        // HTTPS only
          description:          'Allow inbound HTTPS from Internet'
        }
      }

      {
        name: 'AllowHttpInbound'
        properties: {
          priority:             110
          direction:            'Inbound'
          access:               'Allow'
          protocol:             'Tcp'
          sourceAddressPrefix:  'Internet'
          sourcePortRange:      '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '80'          // HTTP — redirect to HTTPS in your app
          description:          'Allow inbound HTTP (redirect to HTTPS)'
        }
      }

      {
        name: 'DenyAllInbound'
        properties: {
          priority:             4000          // very high number = evaluated last
          direction:            'Inbound'
          access:               'Deny'        // deny everything not matched above
          protocol:             '*'
          sourceAddressPrefix:  '*'
          sourcePortRange:      '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '*'
          description:          'Deny all other inbound traffic (explicit deny-all)'
        }
      }
    ]
  }
}

// NSG for the data (database) subnet — only allow traffic from the app subnet
resource dataNsg 'Microsoft.Network/networkSecurityGroups@2023-05-01' = {
  name:     'nsg-data-${env}'
  location: location
  tags:     { environment: env }

  properties: {
    securityRules: [
      {
        name: 'AllowFromAppSubnet'
        properties: {
          priority:             100
          direction:            'Inbound'
          access:               'Allow'
          protocol:             'Tcp'
          sourceAddressPrefix:  appSubnetPrefix    // only allow traffic from app subnet
          sourcePortRange:      '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '5432'             // PostgreSQL default port
          description:          'Allow PostgreSQL from app subnet only'
        }
      }
      {
        name: 'DenyAllInbound'
        properties: {
          priority:             4000
          direction:            'Inbound'
          access:               'Deny'
          protocol:             '*'
          sourceAddressPrefix:  '*'
          sourcePortRange:      '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '*'
        }
      }
    ]
  }
}


// =============================================================================
// VIRTUAL NETWORK — with subnets defined INLINE
// =============================================================================
// Subnets can be declared two ways:
//   1. Inline inside the VNet properties.subnets array  (shown here)
//   2. As separate child resources with parent: vnet    (shown after)
//
// The inline approach is simpler but means you CANNOT use Bicep 'for' loops
// on the subnets array without triggering a known ARM race condition.
// For dynamic subnet lists, use child resource declarations instead.

resource vnet 'Microsoft.Network/virtualNetworks@2023-05-01' = {
  name:     vnetName
  location: location
  tags:     { environment: env }

  properties: {
    addressSpace: {
      addressPrefixes: [
        vnetAddressPrefix             // the VNet's total IP range
      ]
    }

    // Subnets defined inline:
    subnets: [
      {
        name: 'snet-web'
        properties: {
          addressPrefix: webSubnetPrefix            // must be within vnetAddressPrefix
          networkSecurityGroup: {
            id: webNsg.id                           // attach the NSG by its resource ID
            // webNsg.id = symbolic name + .id = the ARM resource ID
            // Bicep sees this reference and automatically deploys webNsg BEFORE vnet
          }
          // serviceEndpoints allow subnets to reach Azure services over the backbone
          serviceEndpoints: [
            { service: 'Microsoft.Storage' }        // direct route to Storage without public IP
            { service: 'Microsoft.Sql' }
          ]
          privateEndpointNetworkPolicies: 'Disabled'   // required to deploy Private Endpoints here
        }
      }

      {
        name: 'snet-app'
        properties: {
          addressPrefix: appSubnetPrefix
          // No NSG here — could add one for tighter control in production
          delegations: [                             // delegation = subnet reserved for a specific service
            {
              name: 'Microsoft.Web.serverFarms'
              properties: {
                serviceName: 'Microsoft.Web/serverFarms'   // delegates subnet to App Service
                // When a subnet is delegated, only that service can use it for injection
              }
            }
          ]
        }
      }

      {
        name: 'snet-data'
        properties: {
          addressPrefix: dataSubnetPrefix
          networkSecurityGroup: {
            id: dataNsg.id
          }
          // Disable private endpoint network policies so we can place private endpoints here
          privateEndpointNetworkPolicies: 'Disabled'
        }
      }
    ]
  }
}


// =============================================================================
// REFERENCING A CHILD RESOURCE (inline subnet) AFTER DEPLOYMENT
// =============================================================================
// Inline subnets are NOT separate resources in Bicep — you reference them
// via the VNet's properties array, not a symbolic name.

var webSubnetId = '${vnet.id}/subnets/snet-web'
// This builds the ARM resource ID for the subnet by hand.
// Format: /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Network/virtualNetworks/<name>/subnets/<subnet>

// Alternatively, use the filter function to find the subnet object:
var webSubnetRef = filter(vnet.properties.subnets, s => s.name == 'snet-web')[0]
// filter(array, condition) returns elements matching the condition
// [0] takes the first (only) match


// =============================================================================
// SEPARATE CHILD RESOURCE APPROACH (for comparison)
// =============================================================================
// If you declared subnets as separate child resources (NOT inline), it looks like:
//
// resource appSubnet 'Microsoft.Network/virtualNetworks/subnets@2023-05-01' = {
//   parent: vnet            // Bicep links this to the vnet symbolic name
//   name: 'snet-app'
//   properties: {
//     addressPrefix: appSubnetPrefix
//   }
// }
//
// Then reference it as: appSubnet.id
// CAUTION: when using separate child resources, add subnets sequentially
// (not in parallel) to avoid ARM 'subnet in use' race conditions — use
// dependsOn or order your declarations carefully.


// =============================================================================
// OUTPUTS
// =============================================================================

output vnetId   string = vnet.id
output vnetName string = vnet.name

// Export subnet IDs for use by other templates (VMs, AKS, etc. need subnet IDs)
output webSubnetId  string = webSubnetId
// For the other subnets, build the IDs the same way:
output appSubnetId  string = '${vnet.id}/subnets/snet-app'
output dataSubnetId string = '${vnet.id}/subnets/snet-data'

output nsgWebId  string = webNsg.id
output nsgDataId string = dataNsg.id


// =============================================================================
// EXERCISES
// =============================================================================
// 1. Add a 'bastion' subnet named 'AzureBastionSubnet' (name is mandatory for Bastion).
//    Give it prefix '10.0.255.0/27' (minimum /27 required by Azure Bastion).
//    Do NOT attach an NSG — Bastion manages its own rules.
//
// 2. Add a new NSG rule to webNsg that ALLOWS inbound SSH (port 22) from
//    a specific IP '1.2.3.4' with priority 200.
//    Why is it dangerous to allow SSH from 'Internet' rather than a specific IP?
//
// 3. Add an output 'subnetCount' of type int showing how many subnets the VNet has.
//    Hint: length(vnet.properties.subnets)
