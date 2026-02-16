View [this link](https://learn.microsoft.com/en-us/azure/ai-foundry/foundry-local/get-started?view=foundry-classic) for further documentation.

### Installation

Windows:
```
winget install Microsoft.FoundryLocal
```

macOS:
```
brew tap microsoft/foundrylocal
brew install foundrylocal
```

After installing, verify the installation:
```foundry --version```

### Uninstallation

Windows:
```
winget uninstall Microsoft.FoundryLocal
```

macOS:
```
brew rm foundrylocal
brew untap microsoft/foundrylocal
brew cleanup --scrub
```

### Useful Commands

To install/run a model (ex. mistral-7b-v0.2), run
```foundry model run mistral-7b-v0.2```

Run ```foundry model list``` to see what models are available for download

Run ```winget upgrade --id Microsoft.FoundryLocal``` (Windows) or ```brew upgrade foundrylocal```(macOS) to update Foundry Local