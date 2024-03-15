from secrets import token_urlsafe
from asyncio import sleep
from bot import (
    LOGGER,
    aria2_options,
    aria2c_global,
    download_dict,
    download_dict_lock,
    non_queued_dl,
    queue_dict_lock,
)
from bot.helper.ext_utils.bot_utils import sync_to_async
from bot.helper.ext_utils.task_manager import is_queued, stop_duplicate_check, limit_checker
from bot.helper.listeners.direct_listener import DirectListener
from bot.helper.mirror_utils.status_utils.direct_status import DirectStatus
from bot.helper.mirror_utils.status_utils.queue_status import QueueStatus
from bot.helper.switch_helper.message_utils import sendMessage, sendStatusMessage, auto_delete_message
from bot import config_dict
async def add_direct_download(listener, path):
    details = listener.link
    if not (contents := details.get("contents")):
        await sendMessage(listener.message, "There is nothing to download!")
        return
    size = details["total_size"]

    if not foldername:
        foldername = details['title']
    path = f'{path}/{foldername}'
    if config_dict['STOP_DUPLICATE']:
        msg, button = await stop_duplicate_check(foldername, listener)
        if msg:
            dmsg = await sendMessage(listener.message, msg, button)
            await auto_delete_message(listener.message, dmsg)
            return
    if any([config_dict['DIRECT_LIMIT'],
            config_dict['LEECH_LIMIT'],
            config_dict['STORAGE_THRESHOLD']]):
        await sleep(1)
        if limit_exceeded := await limit_checker(size, listener):
            LOGGER.info(f"Limit Exceeded: {foldername} | {size}")
            amsg = await sendMessage(listener.message, limit_exceeded)
            await auto_delete_message(listener.message, amsg)
            return

    gid = token_urlsafe(10)
    added_to_queue, event = await is_queued(listener.mid)
    if added_to_queue:
        LOGGER.info(f"Added to Queue/Download: {listener.name}")
        async with download_dict_lock:
            download_dict[listener.mid] = QueueStatus(listener, size, gid, "dl")
        await listener.onDownloadStart()
        if listener.multi <= 1:
            await sendStatusMessage(listener.message)
        await event.wait()
        async with download_dict_lock:
            if listener.mid not in download_dict:
                return
        from_queue = True
    else:
        from_queue = False

    a2c_opt = {**aria2_options}
    [a2c_opt.pop(k) for k in aria2c_global if k in aria2_options]
    if header := details.get("header"):
        a2c_opt["header"] = header
    a2c_opt["follow-torrent"] = "false"
    a2c_opt["follow-metalink"] = "false"
    directListener = DirectListener(size, path, listener, a2c_opt)
    async with download_dict_lock:
        download_dict[listener.mid] = DirectStatus(listener, directListener, gid)

    async with queue_dict_lock:
        non_queued_dl.add(listener.mid)

    if from_queue:
        LOGGER.info(f"Start Queued Download from Direct Download: {listener.name}")
    else:
        LOGGER.info(f"Download from Direct Download: {listener.name}")
        await listener.onDownloadStart()
        if listener.multi <= 1:
            await sendStatusMessage(listener.message)

    await sync_to_async(directListener.download, contents)
