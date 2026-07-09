# Homebrew cask for PDF Vault.
#
# To publish: create a repo named `homebrew-tap` under your GitHub account,
# copy this file to Casks/pdf-vault.rb there, and update sha256 + version
# on each release (values printed by build.sh / shown in release notes).
# Users then install with:
#   brew tap BennPhu/tap && brew install --cask pdf-vault
cask "pdf-vault" do
  version "1.5.0"
  sha256 "REPLACE_WITH_RELEASE_SHA256"

  url "https://github.com/BennPhu/pdf-vault/releases/download/v#{version}/PDF-Vault-#{version}-macos.zip"
  name "PDF Vault"
  desc "Light, 100% local PDF library: organize, merge, split, edit, compress"
  homepage "https://github.com/BennPhu/pdf-vault"

  app "PDF Vault.app"

  zap trash: [
    "~/.pdf_vault_config.json",
  ]
end
