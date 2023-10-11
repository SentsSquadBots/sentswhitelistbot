# Sent's Whitelist Bot
A Discord bot with various features for managing both Squad whitelists and generic Squad permissions (such as `canseeadminchat` and `cameraman`)

The bot is split up into 3 areas;
1. Role-Based Multi-Whitelist Management
   - Allows you to give certain Discord roles a set amount of whitelists. Discord members with that role will be allowed to self-manage the SteamIDs on their whitelist up to the set limit.
   - Example: Configure bot to give the @Whitelist5 (5) whitelists. Each Discord member with this role can choose up to (5) steamIDs to put on their personal whitelist.
   - You can easily integrate this into Patreon subscriptions by configuring Patreon to assign a special role to different tiers of subscribers, and configure the bot to give those same Discord roles a set amount of whitelists. This will fully automate whitelist subscriptions.
3. Squad Group Permissions Management
   - Allows you to link Discord roles to a group of in-game permissions
   - Example: Configure bot to link the @Admin Discord role to the permission string `'reserve,balance,chat,canseeadminchat,teamchange,forceteamchange,cameraman'`. Any Discord member with the @Admin role will receive the configured in-game permissions.
   - Any Discord member who needs to receive permissions **needs** to use the /admin_link command and provide their SteamID. 
5. PayPal Payment Whitelist Integration
   - Requires a production PayPal ClientID and Secret [from here](https://developer.paypal.com/dashboard/applications/production). The Application Name is up to you.
   - Allows Discord members to make PayPal payments to buy a **single** whitelist slot in bulk.
   - Example: Assuming `paypal_singleWhitelistCosts='5'`; Discord member makes a $10 payment to your PayPal, Discord member then links their SteamID to the bot and provides the bot with the email they used to make the payment. Once the payment clears, the bot will automatically give the user whitelist using their SteamID. Since the payment was for $10, the user receives 2 months of whitelist. The bot will automatically remove their whitelist in 2 months. 
