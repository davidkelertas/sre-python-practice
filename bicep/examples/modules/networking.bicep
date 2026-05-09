// =============================================================================
// modules/networking.bicep
// Reusable VNet + subnets module — called by 06_modules.bicep.
// Creates a VNet with three subnets: web, app, data.
// =============================================================================

@description('Azure region to deploy into.')
param location string              // required

@description('Environment name.')
param env string = 'dev'

@description('Address space for the entire VNet (must be a valid CIDR block).')
param vnetAddressPrefix string = '10.0.0.0/16'   // /16 = 65,536 addresses

// Subnet prefixes — each must be a subset of vnetAddressPrefix
param webSubnetPrefix  string = '10.0.1.0/24'    // 256 addresses
param appSubnetPrefix  string = '10.0.2.0/24'
param dataSubnetPrefix string = '10.0.3.0/24'


// --- Virtual Network with inline subnets ---
resource vnet 'Microsoft.Network/virtualNetworks@2023-05-01' = {
  name:     'vnet-${env}'
  location: location
  tags:     { environment: env, managedBy: 'bicep' }

  properties: {
    addressSpace: {
      addressPrefixes: [ vnetAddressPrefix ]
    }

    subnets: [
      {
        name: 'snet-web'
        properties: {
          addressPrefix: webSubnetPrefix
          // Service endpoints let the subnet reach Azure Storage/SQL over the backbone
          serviceEndpoints: [
            { service: 'Microsoft.Storage' }
          ]
          privateEndpointNetworkPolicies: 'Disabled'
        }
      }
      {
        name: 'snet-app'
        properties: {
          addressPrefix: appSubnetPrefix
          // Delegate this subnet to App Service VNet Integration
          delegations: [
            {
              name: 'appservice'
              properties: { serviceName: 'Microsoft.Web/serverFarms' }
            }
          ]
        }
      }
      {
        name: 'snet-data'
        properties: {
          addressPrefix: dataSubnetPrefix
          privateEndpointNetworkPolicies: 'Disabled'   // required for private endpoints
        }
      }
    ]
  }
}


// --- Outputs ---
// Callers need subnet IDs to place VMs, AKS nodes, App Services, etc.

output vnetId   string = vnet.id
output vnetName string = vnet.name

// Build subnet IDs by appending the well-known path to the VNet ID.
// Inline subnets are NOT separate Bicep resources so they have no symbolic name —
// we construct their IDs manually.
output webSubnetId  string = '${vnet.id}/subnets/snet-web'
output appSubnetId  string = '${vnet.id}/subnets/snet-app'
output dataSubnetId string = '${vnet.id}/subnets/snet-data'

output vnetAddressPrefix string = vnetAddressPrefix
