# Sent's Whitelist Bot
A Discord bot with various features for managing both Squad whitelists and generic Squad permissions (such as `canseeadminchat` and `cameraman`)

## Features Overview
The bot is split up into 4 areas;
1. Role-Based Multi-Whitelist Management
   - Allows you to give certain Discord roles a set amount of whitelists. Discord members with that role will be allowed to self-manage the SteamIDs on their whitelist up to the set limit.
   - Example: Configure bot to give the @Whitelist5 (5) whitelists. Each Discord member with this role can choose up to (5) steamIDs to put on their personal whitelist.
   - You can easily integrate this into Patreon subscriptions by configuring Patreon to assign a special role to different tiers of subscribers, and configure the bot to give those same Discord roles a set amount of whitelists. This will fully automate whitelist subscriptions.
![multiwl](https://github.com/SentsSquadBots/sentswhitelistbot/assets/121533452/df23382b-2574-4ee3-a73f-a4508036c720)
2. Squad Group Permissions Management
   - Allows you to link Discord roles to a group of in-game permissions
   - Example: Configure bot to link the @Admin Discord role to the permission string `'reserve,balance,chat,canseeadminchat,teamchange,forceteamchange,cameraman'`. Any Discord member with the @Admin role will receive the configured in-game permissions.
   - Any Discord member who needs to receive permissions **needs** to use the /admin_link command and provide their SteamID. 
![squadgroups](https://github.com/SentsSquadBots/sentswhitelistbot/assets/121533452/77649fea-232c-4d74-960a-b4ca47f9ef0d)
3. PayPal Payment Whitelist Integration
   - Requires a production PayPal ClientID and Secret [from here](https://developer.paypal.com/dashboard/applications/production). The Application Name is up to you.
   - Allows Discord members to make PayPal payments to buy a **single** whitelist slot in bulk.
   - Example: Assuming `paypal_singleWhitelistCosts='5'`; Discord member makes a $10 payment to your PayPal, Discord member then links their SteamID to the bot and provides the bot with the email they used to make the payment. Once the payment clears, the bot will automatically give the user whitelist using their SteamID. Since the payment was for $10, the user receives 2 months of whitelist. The bot will automatically remove their whitelist in 2 months. 
4. Clan Whitelist Management
   - Allows anyone with the same clan role to edit the SteamIDs on the clan's whitelist.
   - Number of whitelists can be configured on a per-clan basis.
![Discord_2023-10-12_07-47-36](https://github.com/SentsSquadBots/sentswhitelistbot/assets/121533452/02dfc29f-11aa-4e73-9351-39262c0bab65)

## Running The Bot
This bot was designed to run using [Docker](https://www.docker.com/). A Docker image is automatically built and is available from this repo (`ghcr.io/sentssquadbots/sentswhitelistbot:latest`). The only prerequisite to run this bot is to install Docker first. 

Easiest way to install Docker on a Linux OS is:

`curl -fsSL https://get.docker.com -o install-docker.sh`

`sudo sh install-docker.sh`

I also suggest adding yourself to the `docker` group so you can use Docker without sudo: `sudo usermod -aG docker $USER`. (relog to take effect)

### Run it
Once Docker is installed, all you need to do to run the bot is:
1. Create a folder for the bot's files to live -> `cd ~ && mkdir whitelistbot && cd whitelistbot`
2. Download the compose file -> `wget https://raw.githubusercontent.com/SentsSquadBots/sentswhitelistbot/main/compose.yml`
3. Download the example .env file -> `wget https://raw.githubusercontent.com/SentsSquadBots/sentswhitelistbot/main/exampleENV.env -O .env`
4. Edit the `.env` file -> `nano .env` see [Configuration](#configuration)
3. Start the bot -> `docker compose up -d`

### Update it
To update the bot with the latest release:

1. `docker compose down`
2. `docker compose pull`
3. `docker compose up -d`

### View Logs
To check the logs:

`docker logs -fn30 whitelistbot`

### Windows or without Docker
If you want to run on this on Windows, you can install Docker Desktop and WSL:
- Install Docker: https://docs.docker.com/desktop/install/windows-install/
- Install WSL: in an admin powershell: `wsl --install`

Follow the steps above inside of WSL.

If you want to run the bot without Docker, you will need to install Python and all the packages from `requirements.txt` yourself, plus you will need to serve the cfg files as well.

## Limit Command Usage
The bot has multiple /slashcommands. The public members of your server should not have access to these commands. By default all commands will only be useable by server administrators. If you would like to allow specific roles to use the commands, go into your server's settings -> Integrations -> and add roles or members to the different command groups.

![Disable Command Access](https://i.imgur.com/ZoNavuU.png)

## Adding the CFG's to Squad's RemoteAdminListHosts.cfg
The bot generates .cfg files and places them into the folder as defined in the `host_cfg_folder` env variable. (Default is a folder named `cfgs` in the same folder as the `compose.yml`)

The compose includes a simple NGINX server which serves all files inside `host_cfg_folder` on port 8080 by default. If you use all the features and all defaults, the files would be:
- http://127.0.01:8080/squadadmins.cfg
- http://127.0.01:8080/paypalwls.cfg
- http://127.0.01:8080/clanwls.cfg
- http://127.0.01:8080/monthlywls.cfg

If the bot is running on a remote server, such as a VPS, use the machine's public IP instead of `127.0.0.1`. You can change the port from `8080` if there is a conflict by editing the `compose.yml` file.

## Configuration
- All configuration is done via environment variables. The `compose.yml` will automatically load all variables from a `bot.env` file that is in the same folder as the compose.
- Download the example .env file and rename it to `bot.env` -> `wget https://raw.githubusercontent.com/SentsSquadBots/sentswhitelistbot/main/exampleENV.env -O bot.env`

See each section below for info on configuring the bots features.

### Required configuration
These are the minimum variables you need to change:
- `CommunityName= "Your Community Name Here"`
- `CommunityLogoUrlPNG= "https://i.imgur.com/NpN0xYj.jpeg"`
- `DiscordServer_ID= "0"`
  - Enable Developer Mode under Discord Advanced settings, right-click your server -> Copy Server ID
- `discord_token= "XXXXX"`
  - Get token from https://discord.com/developers/
- `steam_API_key= "XXXX1234"`
  - Get from https://steamcommunity.com/dev/apikey
- `do_log= "false"`
  - Recommend setting to `"true"` and putting the Channel ID of the logging channel below.
- `log_channel_ID= "0"`

### 1. Multi-Whitelist configuration
The basic configuration for this feature is configured in Discord using the `/multiwl` set of commands. This feature is always available, but if you don't want to use it simply don't configure it or send the panel anywhere.

An example setup:
- `/multiwl linkrole role:@whitelist-1 maxwhitelists:1`
- `/multiwl linkrole role:@whitelist-2 maxwhitelists:2`
- `/multiwl sendpanel channel:#whitelist`

Users can now self-manage their whitelists in the channel you sent the Panel to. You can automate **Patreon Tiers** by making Patreon assign a different specific role to each tier, then link that role with a number of whitelists. That way, when a user subscribes on Patreon, they will get a certain number of whitelists depending on what tier they subscribe to.

### 2. Squad Groups configuration
You need to change the following environment variable:
- `featureEnable_SquadGroups= "false"`
  - set to `"true"` to use this feature.

All remaining configuration is done in Discord with the `/groups` set of commands. An example for setting up an Admin group:
- `/groups create name:Admin`
- `/groups link group:Admin role:@Admin`
- `/groups edit groupname:Admin`
  - Paste in `reserve,balance,chat,canseeadminchat,teamchange,forceteamchange,cameraman` for the permissions.
-  Finally, all your Admins must inform the bot of their SteamID by using `/adminlink steamid:YourSteamIDhere`

### 3. PayPal Whitelist configuration
You need to change the following environment variables:
- `featureEnable_Paypal= "false"`
   - set to `"true"` to use this feature.
- `paypal_clientID= "XXXX"`
- `paypal_clientSecret= "XXXX"`
  - Get the ClientID and Secret from https://developer.paypal.com/dashboard/applications/production
- `paypal_checkoutLink= "https://www.google.com"`
  - The link to your PayPal page, so the bot can direct users.
- `paypal_singleWhitelistCosts= "5"`
  - How much does 30 days of whitelist cost? Whole numbers only.
- `paypal_roles= "[]"`
  - If you want the bot to give a role or roles when applying whitelist, put the IDs of the roles here
  - Format examples: single role: `"[1064951253131599882]"` , multiple roles: `"[1064951253131599882, 110123213232132122]"`

### 4. Clan Whitelist configuration
You need to change the following environment variables:
- `featureClanWhitelists= "false"`
   - set to `"true"` to use this feature.
- `clanWhitelists= "{}"`
  - format example: `"{'1066815293885780038':{'numWhitelists': 20}}"`. This would give the clan role 1066815293885780038 20 whitelists that anyone with that role can edit.
  - example with multiple clans: `"{'1066815293885780038':{'numWhitelists': 20}, '110123213232132122':{'numWhitelists': 10}}"`
