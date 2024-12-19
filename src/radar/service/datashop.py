#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import glob
import json
import time
import yaml
import radar
import pprint
import random
import logging
import argparse
import textwrap
import threading
import setproctitle

__prog__ = "datashop"
logger = logging.getLogger(__prog__)
if sys.version_info[:3] < (3, 8, 0):
    pp = pprint.PrettyPrinter(indent=1, depth=3, width=120)
else:
    pp = pprint.PrettyPrinter(indent=1, depth=3, width=120, sort_dicts=False)


def request(client, file, verbose=0):
    if verbose:
        print(f"Req: {file} ...")
    data = client.get(file)
    if data is None:
        logger.info(f"Ign: {file} ...")
        return None
    unixTime = data["time"]
    timeString = time.strftime(r"%Y%m%d-%H%M%S", time.localtime(unixTime))
    basename = os.path.basename(file)
    elements = basename.split("-")
    fileTime = f"{elements[1]}-{elements[2]}"
    mark = radar.cosmetics.check if fileTime == timeString else radar.cosmetics.cross
    print(f"Out: {basename} / {timeString} {mark}")
    return data


def test(args):
    if not os.path.exists(args.test):
        print(f"Directory {args.test} does not exist")
        return
    files = sorted(glob.glob(os.path.join(args.test, "*xz")))
    print(f"Initializing ... port = {args.port}  len(files) = {len(files)}")
    client = radar.product.Client(count=6, port=args.port, verbose=args.verbose)
    tic = time.time()
    fifo = radar.FIFOBuffer()
    for file in files[-200:-100] if len(files) > 200 else files[:100]:
        req = threading.Thread(target=request, args=(client, file, args.verbose))
        req.start()
        fifo.enqueue(req)
        while fifo.size() >= client.count * 2:
            req = fifo.dequeue()
            req.join()
        # Simulate delays
        if args.delay:
            period = random.randint(0, 13)
            if args.verbose > 1:
                print(f"Sleeping for {period} second{'s' if period > 1 else ''} ...")
            client._shallow_sleep(period)
    for req in fifo.queue:
        req.join()
    toc = time.time()

    print(f"Elapsed: {toc - tic:.3f} s")
    print("Passed")

    client.stop()
    return 0


def main():
    parser = argparse.ArgumentParser(
        prog=__prog__,
        formatter_class=argparse.RawTextHelpFormatter,
        description=textwrap.dedent(
            f"""\
        Datashop

        Examples:
            {__prog__} -v settings.yaml
        """
        ),
        epilog="Copyright (c) Boonleng Cheong",
    )
    parser.add_argument("source", nargs="*", help="configuration")
    parser.add_argument("-c", "--count", type=int, default=None, help="count")
    parser.add_argument("-d", "--dir", type=str, default=None, help="directory")
    parser.add_argument("-l", "--logfile", type=str, default=None, help="log file")
    parser.add_argument("-p", "--port", type=int, default=None, help="port")
    parser.add_argument("-t", "--test", action=None, help="test using directory")
    parser.add_argument("-v", dest="verbose", default=0, action="count", help="increases verbosity")
    parser.add_argument("--delay", action="store_true", help="simulate request delays")
    parser.add_argument("--version", action="version", version="%(prog)s " + radar.__version__)
    parser.add_argument("--no-log", action="store_true", help="do not log to file")
    args = parser.parse_args()

    # Set the process title for easy identification
    setproctitle.setproctitle(f"{__prog__} {' '.join(sys.argv[1:])}")

    # Read the configuration file
    config_file = args.source[0] if len(args.source) else "settings.yaml"
    if os.path.exists(config_file):
        _, config_ext = os.path.splitext(config_file)
        if config_ext == ".json":
            with open(config_file) as f:
                config = json.load(f)
        elif config_ext == ".yml" or config_ext == ".yaml":
            with open(config_file) as f:
                config = yaml.safe_load(f)
        else:
            logger.error(f"Unsupported configuration {config_ext}")
            sys.exit(1)
    else:
        config = {}

    # Logfile from configuration, override by command line
    logfile = args.logfile or config.get("logfile", "datashop.log")
    # Add FileHandler to always log INFO and above to a file
    file_handler = logging.FileHandler(logfile)
    file_handler.setFormatter(radar.logFormatter)
    logger.addHandler(file_handler)
    # Add StreamHandler to log to console when verbose > 0
    if args.verbose:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(radar.logFormatter)
        logger.addHandler(stream_handler)
    # Set logger level to INFO by default
    if args.verbose > 1:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    logger.info(f"Datashop {radar.__version__}")

    # Test the function
    if args.test:
        test(args)
        sys.exit(0)

    # Override other configuration by command line
    if args.count:
        config["count"] = args.count
    if args.port:
        config["port"] = args.port

    if args.verbose > 1:
        logger.debug(pp.pformat(config))

    server = radar.product.Server(logger=logger, **config)
    server.start()

    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt ...")
        pass

    server.join()
    logger.info("Done")


###

if __name__ == "__main__":
    main()
