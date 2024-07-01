# Sales Order Sync

## Background Job

Every hour, a background task runs that performs the following steps:
1. Retrieve a list of **WooCommerce Orders** that have been modified since the *Last Syncronisation Date* (on **WooCommerce Integration Settings**) 
2. Retrieve a list of ERPNext **Sales Orders** that are already linked to the **WooCommerce Orders** from Step 1
3. Retrieve a list of ERPNext **Sales Orders** that have been modified since the *Last Syncronisation Date* (on **WooCommerce Integration Settings**)
4. If necessary, retrieve a list of **WooCommerce Orders** that are already linked to the ERPNext **Sales Orders** from Step 3
5. Compare each **WooCommerce Order** with its ERPNext **Sales Orders** counterpart, creating an order if it doesn't exist

## Synchronisation Logic
When comparing a **WooCommerce Order** with it's counterpart ERPNext **Sales Order**, the `date_modified` field on **WooCommerce Order** is compared with the `modified` field of ERPNext **Sales Order**. The last modified document will be used as master when syncronising

## Fields Mapping

| WooCommerce | ERPNext                                       | Note                                                                                                                             |
| ----------- | --------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| billing     | **Address** with type *Billing*               | Checks if the `email` field matches an existing **Customer's** `woocommerce_email` field. If not, a new **Customer** is created. |
|             | **Contact**                                   |                                                                                                                                  |
| shipping    | **Adress** with type *Shipping*               |                                                                                                                                  |
| line_items  | **Item**                                      | Checks if a linked **Item** exists, else a new Item is created                                                                   |
| id          | **Sales Order** > *Customer's Purchase Order* |                                                                                                                                  |
|             | **Sales Order** > *Woocommerce ID*            |                                                                                                                                  |
| currency    | **Sales Order** > *Currency*                  |                                                                                                                                  |



## Troubleshooting
- You can look at the list of **WooCommerce Orders** from within ERPNext by opening the **WooCommerce Order** doctype. This is a [Virtual DocType](https://frappeframework.com/docs/v15/user/en/basics/doctypes/virtual-doctype) that interacts directly with your WooCommerce site's API interface
- Any errors during this process can be found under **Error Log**.
- You can also check the **Scheduled Job Log** for the `sync_sales_orders.run_sales_orders_sync` Scheduled Job.
- A history of all API calls made to your Wordpress Site can be found under **WooCommerce Request Log**

