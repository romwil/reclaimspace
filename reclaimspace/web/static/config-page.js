/** Configuration page bootstrap. */

async function bootstrapConfig() {
  initHeaderNav();
  bindSetupWizardButtons();
  loadHealth();
  loadSetupHealth();
  initSettingsPage();
}

bootstrapConfig().catch((error) => {
  showBootstrapError(error);
});
