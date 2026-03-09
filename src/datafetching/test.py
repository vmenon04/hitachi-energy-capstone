from azure.identity import DefaultAzureCredential

cred = DefaultAzureCredential()
token = cred.get_token("https://graph.microsoft.com/.default")

print(token.token)