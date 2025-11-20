@description('Azure region for the majority of resources (Storage, SQL, Search, etc.)')
param location string = 'eastus2'

@description('Azure region for the Azure OpenAI account')
param openAiLocation string = 'eastus'

@description('Azure region for the Cosmos DB account')
param cosmosLocation string = 'eastus2'

@description('Name of the Azure OpenAI (Cognitive Services) account')
param openAiAccountName string = 'ingeniousopenai'

@description('Name of the Azure SQL Server (must be globally unique)')
param sqlServerName string = 'ingensqlsrv01'

@description('Administrator login for the Azure SQL Server')
param sqlAdministratorLogin string = 'ingenadmin'

@description('Administrator password for the Azure SQL Server')
@secure()
param sqlAdministratorPassword string

@description('Name of the Azure SQL Database')
param sqlDatabaseName string = 'ingeniousdb'

@description('Name of the Storage Account (must be globally unique)')
param storageAccountName string = 'ingeniousstorageacc'

@description('Name of the Blob container used for prompt storage')
param storageContainerName string = 'prompts'

@description('Name of the Cosmos DB account (must be globally unique)')
param cosmosAccountName string = 'ingeniouscosmosdb'

@description('Name of the Cosmos DB SQL database')
param cosmosDatabaseName string = 'ingenious-db'

@description('Name of the Azure AI Search service (must be globally unique)')
param searchServiceName string = 'ingenioussearchsvc'

@description('Optional public IPv4 address to allow through the SQL server firewall (leave empty to skip)')
param clientIpAddress string = ''

@description('Capacity for the gpt-5-mini deployment (requests/minute)')
param gpt5MiniCapacity int = 120

@description('Capacity for the text-embedding-3-small deployment (requests/minute)')
param embeddingCapacity int = 300

// Azure OpenAI (Cognitive Services) account
resource cognitiveAccount 'Microsoft.CognitiveServices/accounts@2023-05-01' = {
  name: openAiAccountName
  location: openAiLocation
  kind: 'OpenAI'
  sku: {
    name: 'S0'
  }
  properties: {
    publicNetworkAccess: 'enabled'
  }
}

// gpt-5-mini deployment
resource gpt5Deployment 'Microsoft.CognitiveServices/accounts/deployments@2023-05-01' = {
  name: 'gpt-5-mini'
  parent: cognitiveAccount
  sku: {
    name: 'Standard'
    capacity: gpt5MiniCapacity
  }
  properties: {
    model: {
      name: 'gpt-5-mini'
      format: 'OpenAI'
      version: '2024-07-18'
    }
    versionUpgradeOption: 'OnceNewDefaultVersionAvailable'
  }
}

// text-embedding-3-small deployment
resource embeddingDeployment 'Microsoft.CognitiveServices/accounts/deployments@2023-05-01' = {
  name: 'text-embedding-3-small-deployment'
  parent: cognitiveAccount
  sku: {
    name: 'Standard'
    capacity: embeddingCapacity
  }
  properties: {
    model: {
      name: 'text-embedding-3-small'
      format: 'OpenAI'
      version: '1'
    }
    versionUpgradeOption: 'OnceNewDefaultVersionAvailable'
  }
}

// Azure SQL Server
resource sqlServer 'Microsoft.Sql/servers@2022-05-01-preview' = {
  name: sqlServerName
  location: location
  properties: {
    administratorLogin: sqlAdministratorLogin
    administratorLoginPassword: sqlAdministratorPassword
    publicNetworkAccess: 'enabled'
    minimalTlsVersion: '1.2'
    version: '12.0'
  }
}

// Firewall rule for Azure services
resource allowAzureFirewall 'Microsoft.Sql/servers/firewallRules@2022-05-01-preview' = {
  name: 'AllowAzureServices'
  parent: sqlServer
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

// Optional firewall rule for a specific client IP
resource allowClientIpFirewall 'Microsoft.Sql/servers/firewallRules@2022-05-01-preview' = if (!empty(clientIpAddress)) {
  name: 'AllowClientIp'
  parent: sqlServer
  properties: {
    startIpAddress: clientIpAddress
    endIpAddress: clientIpAddress
  }
}

// Azure SQL Database
resource sqlDatabase 'Microsoft.Sql/servers/databases@2022-05-01-preview' = {
  name: sqlDatabaseName
  parent: sqlServer
  location: location
  sku: {
    name: 'Basic'
    tier: 'Basic'
    capacity: 5
  }
  properties: {
    readScale: 'Disabled'
  }
}

// Storage account for prompts
resource storageAccount 'Microsoft.Storage/storageAccounts@2022-09-01' = {
  name: storageAccountName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
    publicNetworkAccess: 'Enabled'
  }
}

// Default blob service configuration
resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2022-09-01' = {
  name: 'default'
  parent: storageAccount
  properties: {
    cors: {
      corsRules: []
    }
    deleteRetentionPolicy: {
      enabled: false
      allowPermanentDelete: false
    }
  }
}

// Container for prompt storage
resource promptContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2022-09-01' = {
  name: storageContainerName
  parent: blobService
  properties: {
    publicAccess: 'None'
    defaultEncryptionScope: '$account-encryption-key'
    denyEncryptionScopeOverride: false
  }
}

// Cosmos DB account
resource cosmosAccount 'Microsoft.DocumentDB/databaseAccounts@2023-04-15' = {
  name: cosmosAccountName
  location: cosmosLocation
  kind: 'GlobalDocumentDB'
  properties: {
    enableAutomaticFailover: true
    isVirtualNetworkFilterEnabled: false
    publicNetworkAccess: 'enabled'
    databaseAccountOfferType: 'Standard'
    minimalTlsVersion: 'Tls12'
    defaultIdentity: 'FirstPartyIdentity'
    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'
    }
    analyticalStorageConfiguration: {
      schemaType: 'WellDefined'
    }
    locations: [
      {
        locationName: cosmosLocation
        failoverPriority: 0
        isZoneRedundant: false
      }
    ]
  }
}

// Cosmos DB SQL database
resource cosmosSqlDatabase 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2023-04-15' = {
  name: cosmosDatabaseName
  parent: cosmosAccount
  location: cosmosLocation
  properties: {
    resource: {
      id: cosmosDatabaseName
    }
    options: {}
  }
}

// Azure AI Search service
resource searchService 'Microsoft.Search/searchServices@2023-11-01' = {
  name: searchServiceName
  location: location
  sku: {
    name: 'basic'
  }
  properties: {
    authOptions: {
      apiKeyOnly: {}
    }
    publicNetworkAccess: 'enabled'
    replicaCount: 1
    partitionCount: 1
    hostingMode: 'default'
    disableLocalAuth: false
    encryptionWithCmk: {
      enforcement: 'Unspecified'
    }
    semanticSearch: 'free'
  }
}

output cognitiveAccountId string = cognitiveAccount.id
output sqlServerId string = sqlServer.id
output sqlDatabaseId string = sqlDatabase.id
output storageAccountId string = storageAccount.id
output cosmosAccountId string = cosmosAccount.id
output searchServiceId string = searchService.id
