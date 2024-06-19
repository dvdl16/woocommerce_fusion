# Configure WooCommerce Fusion

---

The first step is to create a **WooCommerce Server** document, representing your WooCommerce website.

![click on Add WooCommerce Server](images/add-wc-server.png)

Complete the "WooCommerce Server URL", "API consumer key" and "API consumer secret" fields. To find your API consumer key and secret, go to your WordPress admin panel and navigate to WooCommerce > Settings > Advanced > REST API, and click on "Add key". Make sure to add Read/Write permissions to the API key.

![WooCommerce API Settings](images/wc-api-settings.png)

![New WooCommerce Server](images/new-wc-server.png)

---

Click on the "Sales Orders" tab and complete the mandatory fields

!["Sales Orders" tab](images/so-tab-mandatory.png)

**Settings**:
- Synchronise Sales Order Line changes back

When set, adding/removing/changing Sales Order Lines will be synchronised back to the WooCommerce Order.

---

Click on the "Save" - and you are ready to go!
