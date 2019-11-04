import discord
import coc
import asyncio
import re
import requests

from discord.ext import commands
from cogs.utils.converters import ClanConverter
from cogs.utils.db import Sql
from cogs.utils import helper
from config import settings, color_pick
from datetime import datetime


class CouncilCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="form", aliases=["magic"], hidden=True)
    @commands.has_role(settings['rcs_roles']['council'])
    async def magic_form(self, ctx):
        link = "https://docs.google.com/forms/d/e/1FAIpQLScnSCYr2-qA7OHxrf-z0BZFjDr8aRvvHzIM6bIMTLVtlO16GA/viewform"
        if ctx.channel.id == settings['rcs_channels']['council']:
            await ctx.send(link)
        else:
            await ctx.send("I think I'll respond in the private council channel.")
            channel = self.bot.get_channel(settings['rcsChannels']['council'])
            await channel.send(link)

    @commands.command(name="userinfo", aliases=["ui"], hidden=True)
    @commands.has_any_role(settings['rcs_roles']['council'], settings['rcs_roles']['chat_mods'])
    async def user_info(self, ctx, user: discord.Member):
        """Command to retreive join date and other info for Discord user."""
        today = datetime.now()
        create_date = user.created_at.strftime("%d %b %Y")
        create_delta = (today - user.created_at).days
        join_date = user.joined_at.strftime("%d %b %Y")
        join_delta = (today - user.joined_at).days
        conn = self.bot.pool
        sql = "SELECT MAX(last_message) FROM rcs_discord WHERE discord_id = $1"
        row = conn.fetchrow(sql, user.id)
        last_message = row[0]
        user_roles = []
        for role in user.roles:
            if role.name != "@everyone":
                user_roles.append(role.name)
        embed = discord.Embed(title=user.display_name,
                              description=f"{user.name}#{user.discriminator}",
                              color=color_pick(255, 165, 0))
        embed.set_thumbnail(url=user.avatar_url)
        embed.add_field(name="Joined RCS Server on", value=f"{join_date}\n({join_delta} days ago)", inline=True)
        embed.add_field(name="Discord Creation Date", value=f"{create_date}\n({create_delta} days ago)", inline=True)
        embed.add_field(name="Last Message", value=last_message, inline=False)
        embed.add_field(name="Roles", value=", ".join(user_roles), inline=False)
        embed.set_footer(text=f"User ID: {user.id}")
        await ctx.send(embed=embed)

    @commands.command(name="addClan", aliases=["clanAdd", "newClan", "add_clan", "new_clan"], hidden=True)
    @commands.has_role(settings['rcs_roles']['council'])
    async def add_clan(self, ctx, *, clan_tag: str = "x"):
        """Command to add a new verified clan to the RCS Database."""
        def check_author(m):
            return m.author == ctx.author

        def process_content(content):
            if content.lower() in ["stop", "cancel", "quit"]:
                self.bot.logger.info(f"Process stopped by user ({ctx.command}, {ctx.author})")
                return content, 1
            if content.lower() == "none":
                return "", 0
            return content, 0

        short_name = soc_media = desc = classification = subreddit = leader_reddit = discord_tag = ""

        continue_flag = 1
        # Get clan tag
        if clan_tag == "x":
            try:
                await ctx.send("Please enter the tag of the new clan.")
                response = await ctx.bot.wait_for("message", check=check_author, timeout=30)
                clan_name, cancel_flag = process_content(response.content)
            except asyncio.TimeoutError:
                return await ctx.send("Seriously, I'm not going to wait that long. Start over!")
        # Confirm clan name
        try:
            clan = ctx.coc.get_clan(clan_tag)
        except coc.NotFound:
            raise commands.BadArgument(f"{clan_tag} is not a valid clan tag.")
        confirm = await ctx.prompt(f"I'd like to confirm that you want to create a new clan with "
                                   f"the name **{clan.name}**.")
        if not confirm:
            return await ctx.send("Clan creation cancelled by user.")
        # Get leader's in game name
        leader = clan.get_member(role="leader")
        # create short name
        try:
            await ctx.send("Please create a short name for this clan. This will be what danger-bot "
                           "uses to search Discord names. Please/use/slashes/to/include/more/than/one.")
            response = await ctx.bot.wait_for("message", check=check_author, timeout=30)
            short_name, cancel_flag = process_content(response.content)
            if cancel_flag == 1:
                return await ctx.send("Creating of new clan cancelled by user.")
        except asyncio.TimeoutError:
            await ctx.send("OK slow poke. Here's what I'm going to do. I'm going to create this clan "
                           "with the stuff I know, but you'll have to add the rest later!\n**Missing "
                           "info:**\nShort name\nSocial Media\nDescription\nClassification\nSubreddit\n"
                           "Leader's Reddit Username\nLeader's Discord Tag")
            continue_flag = 0
        # Get social media links
        if continue_flag == 1:
            try:
                await ctx.send("Please include social media links as follows:\n[Twitter](https://twitter.com/"
                               "RedditZulu)\nType `none` if there aren't any links to add at this time.")
                response = await ctx.bot.wait_for("message", check=check_author, timeout=45)
                soc_media, cancel_flag = process_content(response.content)
                if cancel_flag == 1:
                    return await ctx.send("Creating of new clan cancelled by user.")
            except asyncio.TimeoutError:
                await ctx.send(f"I'm stopping here.  {clan.name} has been added to the database, but you'll "
                               "need to add the rest at a later time.\n**Missing info:**\nSocial Media\n"
                               "Description\nClassification\nSubreddit\nLeader's Reddit Username\n"
                               "Leader's Discord Tag")
                continue_flag = 0
        # Get Description
        if continue_flag == 1:
            try:
                await ctx.send("Now I need to know a little bit about the clan.  What notes would you like "
                               "stored for this clan?")
                response = await ctx.bot.wait_for("message", check=check_author, timeout=45)
                desc, cancel_flag = process_content(response.content)
                if cancel_flag == 1:
                    return await ctx.send("Creating of new clan cancelled by user.")
            except asyncio.TimeoutError:
                await ctx.send(f"Time's up {ctx.author}. {clan.name} has been added to the database, but "
                               "you'll need to add the rest at a later time.\n**Missing info:**\n"
                               "Description\nClassification\nSubreddit\nLeader's Reddit Username\n"
                               "Leader's Discord Tag")
                continue_flag = 0
        # Get Classification
        if continue_flag == 1:
            prompt = await ctx.prompt(f"Please select the appropriate classification for {clan.name}.\n"
                                      f":one: - General\n"
                                      f":two: - Social\n"
                                      f":three: - Competitive\n"
                                      f":four: - War Farming",
                                      additional_options=4)
            if prompt == 1:
                classification = "gen"
            elif prompt == 2:
                classification = "social"
            elif prompt == 3:
                classification = "comp"
            elif prompt == 4:
                classification = "warFarm"
            else:
                await ctx.send(f"Can't keep up?  Sorry about that. I've added {clan.name} to the database. "
                               f"You'll need to go back later and add the following.\n**Missing info:**\n"
                               f"Classification\nSubreddit\nLeader's Reddit username\nLeader's Discord Tag")
                continue_flag = 0
        # Get subreddit
        if continue_flag == 1:
            try:
                await ctx.send("Please provide the subreddit for this clan (if they are cool enough to have one). "
                               "(no need to include the /r/)\nIf they are lame and don't have a subreddit, "
                               "type `none`.")
                response = await ctx.bot.wait_for("message", check=check_author, timeout=20)
                subreddit, cancel_flag = process_content(response.content)
                if cancel_flag == 1:
                    return await ctx.send("Creating of new clan cancelled by user.")
                if subreddit != "":
                    subreddit = f"https://www.reddit.com/r/{subreddit}"
            except asyncio.TimeoutError:
                await ctx.send(f"Ugh! You've run out of time! I'll add {clan.name} to the database, but you'll "
                               "need to add missing stuff later!\n**Missing info:**\nLeader's Reddit Username\n"
                               "Leader's Discord Tag")
                continue_flag = 0
        # Get Reddit Username of leader
        if continue_flag == 1:
            try:
                await ctx.send(f"Can you please tell me what the reddit username is for {leader}? (No need "
                               "to include the /u/)")
                response = await ctx.bot.wait_for("message", check=check_author, timeout=20)
                leader_reddit, cancel_flag = process_content(response.content)
                if cancel_flag == 1:
                    return await ctx.send("Creating of new clan cancelled by user.")
                if leader_reddit != "":
                    leader_reddit = f"https://www.reddit.com/user/{leader_reddit}"
            except asyncio.TimeoutError:
                await ctx.send(f"I can see we aren't making any progress here. {clan.name} is in the database "
                               "now, but you'll need to do more!\n**Missing info:**\nLeader's reddit username\n"
                               "Leader's Discord Tag")
                continue_flag = 0
        # Get Leader's Discord Tag
        if continue_flag == 1:
            try:
                await ctx.send(f"Saving the best for last!  What's this guy/gal's Discord Tag?  You know, the "
                               "long string of numbers that mean nothing to you, but mean everything to me!")
                response = await ctx.bot.wait_for("message", check=check_author, timeout=15)
                discord_tag, cancel_flag = process_content(response.content)
                if cancel_flag == 1:
                    return await ctx.send("Creating of new clan cancelled by user.")
            except asyncio.TimeoutError:
                await ctx.send(f"You were so close! I'll add {clan.name} to the database now, but you'll "
                               "need to add the **Discord Tag** later.")
        # Log and inform user
        if discord_tag != "":
            print(f"{datetime.now()} - All data collected for {ctx.command}. Adding {clan.name} to database now.")
            await ctx.send(f"All data collected!  Adding to database now.\n**Clan name:** {clan.name}\n"
                           f"**Clan Tag:** #{clan_tag}\n**Leader:** {leader}\n**Short Name:** {short_name}\n"
                           f"**Social Media:** {soc_media}\n**Notes:** {desc}\n**Classification:** "
                           f"{classification}\n**Subreddit:** {subreddit}\n**Leader's Reddit name:** "
                           f"{leader_reddit}\n**Leader's Discord Tag:** {discord_tag}")
        # Add info to database
        with Sql(as_dict=True) as cursor:
            cursor.execute(f"INSERT INTO rcs_data (clanName, clanTag, clanLeader, shortName, socMedia, "
                           f"notes, classification, subReddit, leaderReddit, discordTag)"
                           f"VALUES ('{clan.name}', '{clan_tag}', '{leader}', '{short_name}', '{soc_media}', "
                           f"'{desc}', '{classification}', '{subreddit}', '{leader_reddit}', {discord_tag})")
        await ctx.send(f"{clan.name} has been added.  Please allow 3 hours for the clan to appear in wiki.")
        # force wiki and cache update
        await ctx.send(f"**Next Steps:**\nSend mod invite for META\nUpdate clan directory in META\n"
                       f"Announce the new clan in Discord")
        # Add leader roles
        guild = ctx.bot.get_guild(settings['discord']['rcs_guild_id'])
        is_user, user = is_discord_user(guild, int(discord_tag))
        if not is_user:
            await ctx.send(f"{discord_tag} does not seem to be a valid tag for {leader} or they are not on "
                           "the RCS server yet. You will need to add roles manually.")
        else:
            role_obj = guild.get_role(int(settings['rcs_roles']['leaders']))
            await user.add_roles(role_obj, reason=f"Leaders role added by ++addClan command of rcs-bot.")
            role_obj = guild.get_role(int(settings['rcs_roles']['rcs_leaders']))
            await user.add_roles(role_obj, reason=f"RCS Leaders role added by ++addClan command of rcs-bot.")
            role_obj = guild.get_role(int(settings['rcs_roles']['recruiters']))
            await user.add_roles(role_obj, reason=f"Clan Recruiters role added by ++addClan command of rcs-bot.")
        # Send DM to new leader with helpful links
        member = ctx.guild.get_member(int(discord_tag))
        await member.send(f"Congratulations on becoming a verified RCS clan!  We have added {clan.name} "
                          "to our database and it will appear on the RCS wiki page within the next 3 hours.  "
                          "You should now have the proper Discord roles and be able to see <#298620147424296970> "
                          "and a few other new channels."
                          "\n\n<#308300486719700992> is for the reporting of questionable players. It's not "
                          "necessarily a ban list, but a heads up. If someone with a note in that channel "
                          "joins your clan, you'll receive an alert in <#448918837904146455> letting you."
                          "\n\nThe channels for clan recruitment and events are available to "
                          "you, but if you'd like to add someone else from your clan to help with those "
                          "items, just let one of the Global Chat Mods know (you can @ tag them)."
                          "\n\nFinally, here is a link to some helpful information. "
                          "It's a lot up front, but this will be a great resource going forward. "
                          "https://docs.google.com/document/d/16gfd-BgkGk1bdRmyxIt92BA-tl1NcYk7tuR3HpFUJXg/"
                          "edit?usp=sharing\n\nWelcome to the RCS!")
        self.bot.logger.info(f"{ctx.command} issued by {ctx.author} for {clan.name} (Channel: {ctx.channel})")

    @commands.command(name="removeClan", aliases=["clanRemove", "remove_clan"], hidden=True)
    @commands.has_role(settings['rcs_roles']['council'])
    async def remove_clan(self, ctx, *, clan: ClanConverter = None):
        """Command to remove a verified clan from the RCS database."""
        if not clan:
            return await ctx.send("You have not provided a valid clan name or clan tag.")
        with Sql(as_dict=True) as cursor:
            cursor.execute(f"SELECT clanName, clanTag FROM rcs_data WHERE feeder = '{clan.name}'")
            fetched = cursor.fetchone()
            if fetched is not None:
                self.bot.logger.info(f"Removing family clan for {clan.name}. Issued by {ctx.author} in {ctx.channel}")
                cursor.execute(f"DELETE FROM rcs_data WHERE clanTag = '{fetched['clanTag']}'")
                await ctx.send(f"{fetched['clanName']} (feeder for {clan.name}) has been removed.")
            self.bot.logger.info(f"Removing {clan.name}. Issued by {ctx.author} in {ctx.channel}")
            cursor.execute(f"SELECT leaderReddit, discordTag FROM rcs_data WHERE clanTag = '{clan.tag}'")
            fetched = cursor.fetchone()
            cursor.execute(f"DELETE FROM rcs_data WHERE clanTag = '{clan.tag}'")
        # remove leader's roles
        guild = ctx.bot.get_guild(settings['discord']['rcsGuildId'])
        is_user, user = is_discord_user(guild, int(fetched['discordTag']))
        if is_user:
            role_obj = guild.get_role(int(settings['rcs_roles']['leaders']))
            await user.remove_roles(role_obj,
                                    reason=f"Leaders role removed by ++removeClan command of rcs-bot.")
            role_obj = guild.get_role(int(settings['rcs_roles']['rcs_leaders']))
            await user.remove_roles(role_obj,
                                    reason=f"RCS Leaders role removed by ++removeClan command of rcs-bot.")
            role_obj = guild.get_role(int(settings['rcs_roles']['recruiters']))
            await user.remove_roles(role_obj,
                                    reason=f"Clan Recruiters role removed by ++removeClan command of rcs-bot.")
        await ctx.send(f"{clan.name} has been removed from the database.  The change will appear on the wiki "
                       "in the next 3 hours.")
        # TODO update the wiki
        helper.rcs_clans.clear_cache()
        helper.get_clan.clear_cache()
        await ctx.send("<@251150854571163648> Please recycle the bot so we aren't embarassed with old data!")
        await ctx.send(f"Please don't forget to remove {fetched['leaderReddit'][22:]} as a mod from META and "
                       f"update the META clan directory.  I've removed the Leaders, RCS Leaders, and Clan "
                       f"Recruiters role from <@{fetched['discordTag']}>. If they have any other roles, "
                       f"you will need to remove them manually.")

    @commands.command(name="in_war", aliases=["inwar"], hidden=True)
    @commands.has_any_role("Admin1", "Leaders", "Council")
    async def in_war(self, ctx):
        async with ctx.typing():
            with Sql(as_dict=True) as cursor:
                cursor.execute("SELECT '#' + clanTag AS tag, isWarLogPublic FROM rcs_data "
                               "WHERE classification <> 'feeder' ORDER BY clanName")
                clans = cursor.fetchall()
            tags = [clan['tag'] for clan in clans if clan['isWarLogPublic'] == 1]
            in_prep = ""
            in_war = ""
            async for war in self.bot.coc.get_current_wars(tags):
                try:
                    if war.state == "preparation":
                        in_prep += (f"{war.clan.name} ({war.clan.tag}) has "
                                    f"{war.start_time.seconds_until // 3600:.0f} hours until war.\n")
                    if war.state == "inWar":
                        in_war += (f"{war.clan.name} ({war.clan.tag}) has "
                                   f"{war.end_time.seconds_until // 3600:.0f} hours left in war.\n")
                except Exception as e:
                    self.bot.logger.exception("get war state")
            await ctx.send_embed(ctx.channel,
                                 "RCS Clan War Status",
                                 "This does not include CWL wars.",
                                 in_prep,
                                 discord.Color.dark_gold())
            await ctx.send_embed(ctx.channel,
                                 "RCS Clan War Status",
                                 "This does not include CWL wars.",
                                 in_war,
                                 discord.Color.dark_red())

    @commands.command(name="leader", hidden=True)
    @commands.has_any_role(settings['rcs_roles']['council'],
                           settings['rcs_roles']['chat_mods'],
                           settings['rcs_roles']['leaders'])
    async def leader(self, ctx, *, clan: ClanConverter = None):
        """Command to find the leader for the selected clan.

        Usage: ++leader Reddit Tau
        """
        if not clan:
            return await ctx.send("You have not provided a valid clan name or clan tag.")
        with Sql(as_dict=True) as cursor:
            cursor.execute(f"SELECT discordTag, clanBadge FROM rcs_data WHERE clanName = '{clan.name}'")
            fetch = cursor.fetchone()
            discord_id = fetch['discordTag']
            badge_url = fetch['clanBadge']
            cursor.execute(f"SELECT altName FROM rcs_alts WHERE clanTag = '{clan.tag[1:]}' ORDER BY altName")
            fetch = cursor.fetchall()
        if fetch:
            alt_names = ""
            for row in fetch:
                alt_names += f"{row['altName']}\n"
        else:
            alt_names = "No alts for this leader"
        embed = discord.Embed(title=f"Leader Information for {clan.name}",
                              color=color_pick(240, 240, 240))
        embed.set_thumbnail(url=badge_url)
        embed.add_field(name="Leader name:",
                        value=f"<@{discord_id}>",
                        inline=False)
        embed.add_field(name="Alt accounts:",
                        value=alt_names,
                        inline=False)
        await ctx.send(embed=embed)

    @commands.group(invoke_without_command=True, hidden=True)
    @commands.has_any_role(settings['rcs_roles']['council'],
                           settings['rcs_roles']['chat_mods'],
                           settings['rcs_roles']['leaders'])
    async def alts(self, ctx):
        """[Group] Command to handle alt accounts of RCS leaders"""
        if ctx.invoked_subcommand is None:
            return await ctx.show_help(ctx.command)

    @alts.command(name="list")
    async def alts_list(self, ctx, *, clan: ClanConverter = None):
        """List alts for the specified clan.
            ++alts list Clan Name
        """
        if clan:
            await ctx.invoke(self.leader, clan=clan)
        else:
            await ctx.send(f"Terribly sorry, but I can't find that clan!")

    @alts.command(name="add")
    async def alts_add(self, ctx, clan: ClanConverter = None, *, new_alt: str = None):
        """Adds new leader alt for the specified clan
            ++alts add "Clan Name" alt name
        """
        if not new_alt:
            return await ctx.send("Please provide the name of the new alt account.")
        with Sql() as cursor:
            sql = (f"INSERT INTO rcs_alts "
                   f"SELECT {clan[0].tag[1:]}, {new_alt} "
                   f"EXCEPT "
                   f"SELECT clanTag, altName FROM rcs_alts WHERE clanTag = {clan[0].tag[1:]} AND altName = {new_alt}")
            cursor.execute(sql)
        await ctx.send(f"{new_alt} has been added as an alt account for the leader of {clan[0].name}.")

    @alts.command(name="remove", aliases=["delete", "del", "rem"])
    async def alts_remove(self, ctx, clan: ClanConverter = None, *, alt: str = None):
        """Remove Leader alt for the specified clan
            ++alts remove "Clan Name" alt name
        """
        if not alt:
            return await ctx.send("Please provide the name of the alt account to be removed.")
        with Sql() as cursor:
            if alt == "all":
                sql = f"DELETE FROM rcs_alts WHERE clanTag = {clan[0].tag[1:]}"
                cursor.execute(sql)
                await ctx.send(f"All alt accounts for {clan[0].name} have been removed.")
            else:
                sql = f"DELETE FROM rcs_alts WHERE clanTag = {clan[0].tag[1:]} AND altName = {alt}"
                cursor.execute(sql)
                await ctx.send(f"{alt} has been removed as an alt for the leader of {clan[0].name}.")

    @commands.group(invoke_without_subcommand=True, hidden=True)
    @commands.has_role(settings['rcs_roles']['council'])
    async def dm(self, ctx):
        """Group command to send DMs to various roles in the RCS Discord Server"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @dm.command(name="leaders", aliases=["leader", "rcsleaders"])
    async def dm_leaders(self, ctx, *, message):
        """Sends message as a DM to all RCS leaders"""
        if not message:
            return await ctx.send("I'm not going to send a blank message you goofball!")
        msg = await ctx.send("One moment while I track down these leaders...")
        with Sql(as_dict=True) as cursor:
            cursor.execute("SELECT DISTINCT discordTag FROM rcs_data")
            rows = cursor.fetchall()
        counter = 0
        for row in rows:
            try:
                member = ctx.guild.get_member(int(row['discordTag']))
                await member.send(message)
                counter += 1
            except:
                self.bot.logger.exception("DM send attempt")
        # Send same message to TubaKid so he knows what's going on
        member = ctx.guild.get_member(251150854571163648)
        await member.send(f"**The following has been sent to all RCS leaders by {ctx.author}**\n\n{message}")
        await msg.edit(f"Message sent to {counter} RCS leaders.")

    @dm.command(name="ayedj", aliases=["dj", "djs"])
    async def dm_djs(self, ctx, *, message):
        """Sends message as a DM to all RCS DJs"""
        if not message:
            return await ctx.send("I don't think the DJs will be impressed with a blank message!")
        msg = await ctx.send("One moment while I spin the turntables...")
        dj_role = ctx.guild.get_role(settings['rcs_roles']['djs'])
        counter = 0
        for member in dj_role.members:
            try:
                await member.send(message)
                counter += 1
            except:
                self.bot.logger.exception("DM send attempt")
        # Send same message to TubaKid so he knows what's going on
        member = ctx.guild.get_member(251150854571163648)
        await member.send(f"**The following has been sent to all RCS DJs by {ctx.author}**\n\n{message}")
        await msg.edit(f"Message sent to {counter} RCS DJs.")

    @commands.command(name="find", aliases=["search"], hidden=True)
    async def find(self, ctx, *, arg: str = "help"):
        """Command to to find a search string in Discord user names"""
        # TODO Figure out the None response on some names
        # TODO add regex or option to only search for string in clan name
        if is_authorized(ctx.author.roles) or 440585276042248192 in ctx.author.roles:
            if arg == "help":
                embed = discord.Embed(title="rcs-bot Help File", 
                                      description="Help for the find/search command", 
                                      color=color_pick(15, 250, 15))
                embed.add_field(name="Commands:", value="-----------")
                help_text = "Used to find Discord names with the specified string."
                embed.add_field(name="++find <search string>", value=help_text)
                embed.set_footer(icon_url="https://openclipart.org/image/300px/svg_to_png/122449/1298569779.png", 
                                 text="rcs-bot proudly maintained by TubaKid.")
                await ctx.send(embed=embed)
                return
            # if not help, code picks up here
            member_role = "296416358415990785"
            guild = str(settings['discord']['rcsGuildId'])

            headers = {"Accept": "application/json", "Authorization": "Bot " + settings['discord']['rcsbotToken']}
            # List first 1000 RCS Discord members
            url = f"https://discordapp.com/api/guilds/{guild}/members?limit=1000"
            r = requests.get(url, headers=headers)
            data1 = r.json()
            # List second 1000 RCS Discord members
            url += "&after=" + data1[999]['user']['id']
            r = requests.get(url, headers=headers)
            data2 = r.json()
            data = data1 + data2

            regex = r"{}".format(arg)
            members = []
            for item in data:
                discord_name, discord_flag = get_discord_name(item)
                if re.search(regex, discord_name, re.IGNORECASE) is not None:
                    report_name = f"""@{item['user']['username']}#{item['user']['discriminator']} - 
                        <@{item['user']['id']}>""" if discord_flag == 1 \
                        else f"@{item['nick']} - <@{item['user']['id']}>"
                    if member_role in item['roles']:
                        report_name += " (Members role)"
                    members.append(report_name)
            if len(members) == 0:
                await ctx.send("No users with that text in their name.")
                return
            content = f"**{arg} Users**\nDiscord users with {arg} in their name.\n\n**Discord names:**\n"
            content += "\n".join(members)
            await self.send_text(ctx.channel, content)
        else:
            print(f"{datetime.now()} - ERROR: {ctx.author} from {ctx.guild} tried to use the ++find command "
                  "but does not have the leader or council role.")
            await ctx.send(f"You have found the secret command!  Unfortunately, you are not an RCS "
                           "Leader/Council member.  Climb the ladder, then try again!")


def get_discord_name(item):
    try:
        if "nick" in item and item['nick'] is not None:
            return item['nick'].lower(), 1
        else:
            return item['user']['username'].lower(), 0
    except:
        print(item)


def is_authorized(user_roles):
    for role in user_roles:
        if role.id in [settings['rcs_roles']['leaders'],
                       settings['rcs_roles']['rcs_leaders'],
                       settings['rcs_roles']['council'],
                       ]:
            return True
    return False


def is_council(user_roles):
    for role in user_roles:
        if role.id == settings['rcs_roles']['council']:
            return True
    return False


def is_chat_mod(user_roles):
    for role in user_roles:
        if role.id == settings['rcs_roles']['chat_mods']:
            return True
    return False


def is_discord_user(guild, discord_id):
    try:
        user = guild.get_member(discord_id)
        if user is None:
            return False, None
        else:
            return True, user
    except:
        return False, None


def setup(bot):
    bot.add_cog(CouncilCog(bot))
