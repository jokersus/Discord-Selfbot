#!/usr/bin/env python3
# -*- mode: python; coding: utf-8 -*-

# This cog by HarJIT may be used, etc in its entirety under the same terms as Appu's selfbot itself (GPLv3).

# This cog may alternatively be used, etc as outlined in the Mozilla Public License (any version).  To be clear, 
# these alternative terms apply to this file alone and not to any other selfbot component or dependency.

# HarJIT supplies this free of charge with no guarantee of safety, fitness, accuracy or anything else.

# Use of >emotedump and dependent commands requires the cogs/utils/image_dump.py helper.
# This is a standard Appu-Selfbot component so this should not be an issue unless you've removed it.

import discord, cogs.utils.checks, discord.ext.commands, discord.errors

import sys, os, asyncio, subprocess, json, collections, getopt, io, time, zlib

# Could try using asyncio for the file io.
# One problem: Microsoft Windows support.
try:
    import _thread as thread
except ImportError:
    import _dummy_thread as thread

# Notes:
# self.mybot.get_channel(id)
# all servers, self.mybot.get_all_channels() (also get_all_emojis take note)
# one server, for channel in server.channels:

numberdict = lambda *a:collections.defaultdict(lambda:0, *a)
numberdictdict = lambda *a: collections.defaultdict(numberdict, *a)
to_numberdictdict = lambda d: numberdictdict(zip(d.keys(), map(numberdict, d.values())))
FakeEmojiObject = collections.namedtuple("FakeEmojiObject", ("name", "url"))

async def softsend(mybot, ctx, f, prefix="", suffix=""):
    if hasattr(mybot, "send_message"):
        send_message = mybot.send_message
    else:
        send_message = (lambda ctx, m: ctx.send(m))
    r = ""
    f.seek(0)
    lines = f.readlines()
    limit = 2000 - len(suffix)
    while lines:
        #print(lines)
        cut = limit - len(r)
        line = lines.pop(0)
        if (len(line) > limit) and (cut > 0):
            # Because pushing on front, have to push in reverse order.
            lines.insert(0, line[cut:])
            lines.insert(0, line[:cut])
        elif len(r + line) > limit:
            lines.insert(0, prefix + line)
            await send_message(ctx.message.channel, r + suffix)
            r = ""
        else:
            r += line
    if r:
        await send_message(ctx.message.channel, r)

async def notification(mybot, ctx, message):
    print("NOTIFY:", message)
    await softsend(mybot, ctx, io.StringIO(mybot.bot_prefix + message))

def get_timestamp():
    if os.path.exists("emotes_timestamp.txt"):
        f = open("emotes_timestamp.txt", "r")
        b = json.load(f)
        f.close()
        return b
    return os.stat("emotes.txt").st_mtime

class DiscEmote2(object):
    """Tools for dumping, and collecting statistics regarding, custom emotes."""
    def __init__(self, mybot):
        self.mybot = mybot

    @discord.ext.commands.command(pass_context = True)
    async def emotescan(self, ctx):
        """Scan the entire current server logs for emote IDs and usage stats, a lengthy process.

        Use --limit=(number) option to limit the number of messages scanned.

        Data is stored in emotes.txt where the other commands will look for it.
        An overview of the most common emote ID to use each name is written to emotes.md"""
        server = ctx.message.server if hasattr(ctx.message, "server") else ctx.message.guild
        argv = ctx.message.content[cogs.utils.checks.cmd_prefix_len():]
        argv = argv.strip().split()
        opts, args = getopt.gnu_getopt(argv[1:], "", ["limit="])
        opts = dict(opts)
        if args:
            await notification(self.mybot, ctx, "Des not accept positional arguments (see help).")
            return
        emoji = numberdictdict()
        qurls = []
        for channel in server.channels:
            qurls.append({"channel": channel, "limit": 99})
        start_time = time.time()
        bigcount = 0
        await notification(self.mybot, ctx, "Commencing emote scan.")
        skips = []
        while qurls:
            qurl = qurls.pop(0)
            if ("before" in qurl) and skips:
                # See also after the loop
                await notification(self.mybot, ctx, 
                      "Skipping %s (non-text or inaccessible)." % (", ".join(skips)))
                skips = []
            channel = qurl["channel"]
            lasti = None
            if hasattr(self.mybot, "logs_from"):
                logs_from = self.mybot.logs_from
            else:
                def logs_from(channel, limit, before=None): 
                    if hasattr(channel, "history"):
                        return channel.history(limit=limit, before=before)
                    return None
            try:
                logsf = logs_from(**qurl)
                if logsf != None:
                    async for i in logsf:
                        bigcount += 1
                        if ("--limit" in opts) and (bigcount > int(opts["--limit"])):
                            break
                        lasti = i
                        for react in i.reactions:
                            if react.custom_emoji:
                                # Old Discord.py API: emoji.id is a str
                                # New Discord.py API: emoji.id is an int
                                # Convert to str to accept both.
                                emoji[react.emoji.name][str(react.emoji.id)] += react.count
                        for j in i.content.split("<:")[1:]:
                            j = j.split(">", 1)[0].split(":")
                            if len(j) == 2:
                                emoji[j[0]][j[1]] += 1
                else:
                    print("Skipping %s (not a text channel?)" % channel.name)
                    skips.append(channel.name)
            except discord.errors.Forbidden:
                print("Channel %s is not accessible." % channel.name)
                skips.append(channel.name)
            except Exception as e:
                await notification(self.mybot, ctx, (str(e)))
            if ("--limit" in opts) and (bigcount > int(opts["--limit"])):
                print("Limit reached.")
                break
            if lasti != None:
                qurls.append({"channel": channel, "limit": 99, "before": lasti})
                # created_at, edited_at
                print("In channel", channel.name, "we are at", lasti.created_at.isoformat())
            else:
                print("Channel", channel.name, "has been completely scanned.")
        if skips: # i.e. no channel had more than one page.
            # See also top of loop
            await notification(self.mybot, ctx, 
                  "Skipped %s (non-text or inaccessible)." % (", ".join(skips)))
            skips = []
        if os.path.exists("emotes.txt"):
            os.rename("emotes.txt", "emotes_%011d.txt" % get_timestamp())
        if os.path.exists("emotes.md"):
            os.rename("emotes.md", "emotes_%011d.md" % get_timestamp())
        if os.path.exists("emotes_timestamp.txt"): # Must be dealt with last for the obvious reasons.
            os.unlink("emotes_timestamp.txt")
        f = open("emotes.txt", "w")
        f.write(json.dumps(emoji))
        f.close()
        f = open("emotes_timestamp.txt", "w")
        f.write(json.dumps(start_time))
        f.close()
        dat = sorted(emoji.items(), key = (lambda b: -sum(b[1].values())))
        f = open("emotes.md","w")
        print("Number of alphacodes:", len(dat), file=f)
        print(file=f)
        print("Number of unique IDs:", sum([len(i) for i in emoji.values()]), file=f)
        print(file=f)
        print("Total number of uses:", sum([sum(i.values()) for i in emoji.values()]), file=f)
        print(file=f)
        for (i,j) in dat:
            print("<:"+i+":"+dict(zip(j.values(),j.keys()))[max(j.values())]+"> with", sum(j.values()), "shortcode uses, of which", max(j.values()), "from that ID", file=f)
            print(file=f)
        f.close()
        await notification(self.mybot, ctx, "Emote scan complete.")

    @discord.ext.commands.command(pass_context = True)
    async def emotedump(self, ctx):
        """Save unsaved emotes for all user's servers plus all emotes found in last emotescan (if available) into emotedump/

        Does not redownload those already saved.  Uses the image_dump mechanism, albeit non-conventionally.

        Use --delay=(number) to set delay in seconds."""
        argv = ctx.message.content[cogs.utils.checks.cmd_prefix_len():]
        argv = argv.strip().split()
        opts = {"--delay": "0"}
        try:
            optsl, args = getopt.gnu_getopt(argv[1:], "", ["delay="])
        except Exception as e:
            await notification(self.mybot, ctx, str(e))
            return
        opts.update(dict(optsl))
        optcf = open("settings/optional_config.json", "r")
        optc = json.load(optcf)
        optcf.close()
        #
        emotelist = []
        for i in (self.mybot.servers if hasattr(self.mybot, "servers") else self.mybot.guilds):
            emotelist.extend(i.emojis)
        if os.path.exists("emotes.txt"):
            await notification(self.mybot, ctx, "Using existing emotescan data.")
            f = open("emotes.txt", "r")
            dat = json.load(f)
            f.close()
            for myname in dat:
                for myid in dat[myname]:
                    #while len(myid) < 18:
                    #    print("reating myid", myid)
                    #    myid = "0" + myid
                    emotelist.append(FakeEmojiObject(myname, myid))
        else:
            await notification(self.mybot, ctx, "Not using emotescan data (not available).")
        emdir = optc["emote_dump_location"] if "emote_dump_location" in optc else "emotedump"
        if os.path.exists(emdir):
            await notification(self.mybot, ctx, "Cleaning up existing dump...")
            for fn in os.listdir(emdir):
                fn1 = os.path.join(emdir, "---".join(fn.rsplit("|", 1)))
                fn2 = os.path.join(emdir, fn)
                if "|" in fn:
                    os.rename(fn2, fn1)
            for fn in os.listdir(emdir): # has to be a second pass
                fn2 = os.path.join(emdir, fn)
                if not os.path.exists(fn2): # i.e. broken symlink
                    otarg = os.readlink(fn2)
                    ntarg = "---".join(otarg.rsplit("|", 1))
                    os.unlink(fn2)
                    os.symlink(ntarg, fn2)
        myemotes = []
        await notification(self.mybot, ctx, "Determining ungrabbed emotes...")
        for i in emotelist:
            myid = i.url.split("/")[-1].split(".")[0]
            myurl = "https://cdn.discordapp.com/emojis/" + myid + ".png"
            myname = i.name
            if not os.path.exists(emdir):
                os.mkdir(emdir)
            fn = os.path.join(emdir, myname + "---" + myid + ".png")
            if not os.path.exists(fn):
                myemotes.append((myurl, fn))
            elif os.stat(fn).st_size == 0: # Empty file from a failed grab
                os.unlink(fn)
                myemotes.append((myurl, fn))
        if not myemotes:
            await notification(self.mybot, ctx, "No ungrabbed emotes to fetch.")
            return
        # ----------------------------------------------------------------------------------------
        myhash = str(abs(hash(tuple(myemotes)))%1000) + str(int(time.time())%1000)
        myurls = tuple(zip(*myemotes))[0]
        f = open("cogs/utils/urlsemotedump%s.txt" % myhash, "w")
        print("\n".join(myurls), file=f)
        f.close()
        root = optc["image_dump_location"] if "image_dump_location" in optc else ""
        iddir = "%simage_dump" % root
        top = os.path.join(iddir, "emotedump" + myhash)
        os.makedirs(top)
        await notification(self.mybot, ctx, "Dumping ungrabbed emotes...")
        idu = subprocess.Popen([sys.executable, "cogs/utils/image_dump.py", root, "emotedump" + myhash, 
                                opts["--delay"], "None", "None", "None", "None", "no"])
        while idu.poll() == None:
            await asyncio.sleep(1)
        fails = []
        for myurl, fn in myemotes:
            targ = os.path.join(top, myurl.split("/")[-1])
            if os.path.exists(targ):
                os.rename(targ, fn)
            else:
                fails.append(fn)
        if fails and (len(fails) < 5):
            await notification(self.mybot, ctx, "Failed to download %s" % ", ".join(fails))
        elif fails:
            await notification(self.mybot, ctx, "Failed to download %d emotes" % len(fails))
        if not os.listdir(top): # not elif
            os.rmdir(top)
        else:
            print("WARNING: %s directory not empty, kept in case." % top)
        await notification(self.mybot, ctx, "Emote dump complete.")

    @discord.ext.commands.command(pass_context = True)
    async def emoteaggregate(self, ctx):
        """Use after an emotescan and subsequent emotedump to calculate aggregate usage counts of emotes.

        That is to say, total number of uses of an identical emote from any source.

        Stored in id2apopu.txt where >emoterank will look for it if directed."""
        optcf = open("settings/optional_config.json", "r")
        optc = json.load(optcf)
        optcf.close()
        emdir = optc["emote_dump_location"] if "emote_dump_location" in optc else "emotedump"
        if not os.path.exists("emotes.txt"):
            await notification(self.mybot, ctx, "No file named emotes.txt - please use >emotescan followed by >emotedump first.")
            return
        if not os.path.exists(emdir):
            await notification(self.mybot, ctx, "No directory named %s - please use >emotedump first." % emdir)
            return
        id2adler = {}
        adler2popu = collections.defaultdict(lambda:0)
        d = json.load(open("emotes.txt"))
        mx = max([len(i) for i in d.values()])
        Popu = collections.namedtuple("Popu", ("name", "pop"))
        await notification(self.mybot, ctx, "Commencing aggregate emote count.")
        complete = []
        # Could try using asyncio for the file io.
        # One problem: Microsoft Windows support.
        allids = set()
        def subthread(id2adler, complete, allids, emdir):
            for f in os.listdir(emdir):
                if "|" in f:
                    nam, mid = os.path.splitext(f)[0].rsplit("|", 1)
                else:
                    nam, mid = os.path.splitext(f)[0].rsplit("---", 1)
                bb = open(os.path.join(emdir, f), "rb").read()
                id2adler[mid] = zlib.adler32(bb)
                if mid:
                    allids.update({mid})
            complete.append(1)
        thread.start_new_thread(subthread, (id2adler, complete, allids, emdir))
        while not complete:
            await asyncio.sleep(1)
        id2apopu = {}
        idfails = []
        idfailmag = 0
        for name in d:
            allids |= set(d[name].keys())
        for name in d:
            for mid in d[name]:
                if mid in id2adler:
                    # Total popularities by adler.
                    # Transfer them to IDs once finished.
                    adler2popu[id2adler[mid]] += d[name][mid]
                else:
                    # ID was not successfully dumped.
                    idfails.append(mid)
                    id2apopu[mid] = d[name][mid] # Better than nothing
                    idfailmag += d[name][mid]
        if idfails:
            await notification(self.mybot, ctx, 
                        "Note %d images not dumped so treated as unique (average %d uses)." % (
                        len(idfails), idfailmag/len(idfails)))
        for mid in id2adler:
            id2apopu[mid] = adler2popu[id2adler[mid]]
        open("id2apopu.txt", "w").write(json.dumps(id2apopu))
        await notification(self.mybot, ctx, "Aggregate emote count complete.")

    @discord.ext.commands.command(pass_context = True)
    async def emoterank(self, ctx):
        """Print rankings from >emotescan data for emotes on current server.

        Use --aggregate option to rank by >emoteaggregate data (i.e. including all sources).
        Use --byname to rank by name only, not by ID.
        Use --byid to rank by id only, not by name."""
        optcf = open("settings/optional_config.json", "r")
        optc = json.load(optcf)
        optcf.close()
        emdir = optc["emote_dump_location"] if "emote_dump_location" in optc else "emotedump"
        server = ctx.message.server if hasattr(ctx.message, "server") else ctx.message.guild
        argv = ctx.message.content[cogs.utils.checks.cmd_prefix_len():]
        argv = argv.strip().split()
        try:
            opts, args = getopt.gnu_getopt(argv[1:], "", ["aggregate", "byname", "byid"])
        except Exception as e:
            await notification(self.mybot, ctx, str(e))
            return
        opts = dict(opts)
        agg = "--aggregate" in opts
        byn = "--byname" in opts
        byi = "--byid" in opts
        if args:
            await notification(self.mybot, ctx, "Des not accept positional arguments (see help).")
            return
        if (agg and byn) or (byn and byi) or (agg and byi):
            await notification(self.mybot, ctx, "Cannot use multiple rank schemes at the same time.")
            return
        emotelist = server.emojis
        if not os.path.exists("emotes.txt"):
            await notification(self.mybot, ctx, "No file named emotes.txt - please use >emotescan first.")
            return
        #print("A")
        date = "%04d-%02d-%02d" % time.gmtime(get_timestamp())[:3]
        f = open("emotes.txt", "r")
        dat = numberdictdict(json.load(f))
        f.close()
        #print("B")
        freqs = collections.defaultdict(lambda:collections.defaultdict(lambda:0))
        allids = set()
        for myname in dat:
            for myid in dat[myname]:
                allids.update({myid})
        #print("C")
        if os.path.exists(emdir):
            for i in os.listdir(emdir):
                i = os.path.splitext(i)[0]
                if "|" in i:
                    mnam, mid = i.split("|")
                else:
                    mnam, mid = i.split("---")
                # Just touch to ensure there is something there.
                dat[mnam] = numberdict(dat[mnam])
                dat[mnam][mid] = dat[mnam][mid]
                allids.update({mid})
        #print("D")
        if agg:
            if not os.path.exists("id2apopu.txt"):
                await notification(self.mybot, ctx, "No file named id2apopu.txt - please use >emoteaggregate first.")
                return
            f = open("id2apopu.txt", "r")
            apopudat = json.load(f)
            f.close()
            allids.update(set(apopudat.keys()))
        elif byi:
            byidat = numberdict()
            for myid in allids:
                for myname in dat:
                    if myid in dat[myname]:
                        byidat[myid] += dat[myname][myid]
        #print("E")
        for myname in dat:
            for myid in dat[myname]:
                if agg:
                    if myid in apopudat:
                        freqs[myname][myid] = apopudat[myid]
                elif byn:
                    freqs[myname][myid] = sum(dat[myname].values())
                elif byi:
                    if byi in byidat:
                        freqs[myname][myid] = byidat[myid]
                else:
                    freqs[myname][myid] = dat[myname][myid]
        u2i = lambda i: i.split("/")[-1].split(".")[0]
        key = lambda emot: -freqs[emot.name][u2i(emot.url)]
        emotelist = sorted(emotelist, key=key)
        #print("F")
        #
        out = io.StringIO()
        print(self.mybot.bot_prefix, file=out)
        print("Data collected on", date, file=out)
        if agg:
            print("Rank for adler32 checksum (includes identical emote from all sources, but not other versions)", file=out)
        elif byn:
            print("Rank for emote name only (includes versions and homonyms, but not identical emote by other names)", file=out)
        elif byi:
            print("Rank for emote ID only (excludes versions and homonyms, excludes identical emote by other IDs)", file=out)
        else:
            print("Ranks for emote name-ID combination (does not include older versions or names, or identical global/nitro emotes)", file=out)
        for i in emotelist:
            print("<:%s:%s> with %s uses" % (i.name, u2i(i.url), -key(i)), file=out)
        await softsend(self.mybot, ctx, out)

    ''' Original implementation, not recommended for use, kept in as a string in case it proves useful to anyone for some reason.
    @discord.ext.commands.command(pass_context = True)
    async def emotedump_wget(self, ctx):
        """Like >emotedump but use an installed wget rather than the image_dump mechanism.
        Said wget should be reasonably GNU compatible (must support the -T and -O options)."""
        try:
            subprocess.call(["wget", "--help"], stdout=subprocess.DEVNULL, stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except EnvironmentError:
            await notification(self.mybot, ctx, ("Requires wget, otherwise use >emotedump instead."))
            return
        emotelist = []
        for i in self.mybot.servers:
            emotelist.extend(i.emojis)
        if os.path.exists("emotes.txt"):
            await notification(self.mybot, ctx, ("Using existing emotescan data."))
            f = open("emotes.txt", "r")
            dat = json.load(f)
            f.close()
            for myname in dat:
                for myid in dat[myname]:
                    emotelist.append(FakeEmojiObject(myname, myid))
        await notification(self.mybot, ctx, ("Commencing emote dump."))
        for i in emotelist:
            myid = i.url.split("/")[-1].split(".")[0]
            myurl = "https://cdn.discordapp.com/emojis/" + myid + ".png"
            myname = i.name
            if not os.path.exists("emotedump"):
                os.mkdir("emotedump")
            print(myurl)
            fn = "emotedump/" + myname + "|" + myid + ".png"
            # Trying to use urllib gets a 403 for some reason
            if (not os.path.exists(fn)) or (os.stat(fn).st_size == 0):
                await asyncio.sleep(1)
                subprocess.call(["wget", "-T", "5", "-O", fn, myurl])
        print("Fin")
        await notification(self.mybot, ctx, ("Emote dump complete."))
    '''

def setup(mybot):
    mybot.add_cog(DiscEmote2(mybot))

