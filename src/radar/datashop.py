#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import json
import time
import yaml
import pprint
import random
import logging
import argparse
import datetime
import textwrap
import threading
import setproctitle

srcDir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src"))
if os.path.exists(srcDir):
    sys.path.insert(0, srcDir)

import radar

__prog__ = "datashop"
logger = logging.getLogger(__prog__)
if sys.version_info[:3] < (3, 8, 0):
    pp = pprint.PrettyPrinter(indent=1, depth=3, width=120)
else:
    pp = pprint.PrettyPrinter(indent=1, depth=3, width=120, sort_dicts=False)
tz = datetime.timezone.utc


def is_foreground():
    return os.isatty(sys.stdin.fileno()) and os.isatty(sys.stdout.fileno()) and os.isatty(sys.stderr.fileno())


def request(client, file, verbose=0):
    if verbose:
        print(f"Req: {file} ...")
    data = client.get(file)
    if data is None:
        logger.info(f"Ign: {file} ...")
        return None
    unixTime = data["time"]
    timeString = datetime.datetime.fromtimestamp(unixTime, tz=tz).strftime(r"%Y%m%d-%H%M%S")
    basename = os.path.basename(file)
    elements = basename.split("-")
    fileTime = f"{elements[1]}-{elements[2]}"
    mark = radar.cosmetics.check if fileTime == timeString else radar.cosmetics.cross
    print(f"Out: {basename} / {timeString} {mark}")
    return data


def test(**kwargs):
    print("kwargs", kwargs)
    folder = kwargs.get("folder")
    verbose = kwargs.get("verbose", 0)
    print(f"Initializing ... port = {kwargs.get('port')}   folder = {folder}")
    client = radar.product.Client(**kwargs)
    fifo = radar.FIFOBuffer()
    tic = time.time()

    files = client.execute("list", folder=folder)

    for file in files:
        req = threading.Thread(target=request, args=(client, file, verbose))
        req.start()
        fifo.enqueue(req)
        while fifo.size() >= client.count * 2:
            req = fifo.dequeue()
            req.join()
        # Simulate delays
        if kwargs.get("delay", False):
            period = random.randint(0, 13)
            if verbose > 1:
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
    parser.add_argument("-H", "--host", type=str, default=None, help="host")
    parser.add_argument("-p", "--port", type=int, default=None, help="port")
    parser.add_argument("-t", "--test", type=str, help="test using directory")
    parser.add_argument("-v", dest="verbose", default=0, action="count", help="increases verbosity")
    parser.add_argument("--delay", action="store_true", help="simulate request delays")
    parser.add_argument("--version", action="version", version="%(prog)s " + radar.__version__)
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
        config = {"host": "localhost", "port": 50000, "count": 4, "cache": 1000, "utc": True}

    # Set logger level to INFO by default
    logging.basicConfig(format=radar.cosmetics.log_format, level=logging.DEBUG if args.verbose else logging.INFO)
    if config.get("utc", False):
        logging.Formatter.converter = time.gmtime

    logger.info(f"Datashop {radar.__version__}")

    # Override other configuration by command line
    if args.host:
        config["host"] = args.host
    if args.port:
        config["port"] = args.port
    if args.count:
        config["count"] = args.count

    if args.verbose > 1:
        logger.debug(pp.pformat(config))

    # Test the function
    if args.test:
        test(**config, folder=args.test, delay=args.delay, verbose=args.verbose)
        sys.exit(0)

    # Start the server
    server = radar.product.Server(logger=logger, signal=True, **config)
    server.start()

    if is_foreground():
        logger.info("Press Ctrl-C to stop ...")
        try:
            while server.wantActive:
                time.sleep(0.1)
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt ...")
            pass
        except:
            logger.info("Something else")
            pass
    else:
        while server.wantActive:
            time.sleep(0.1)

    logger.info("Done")


###

if __name__ == "__main__":
    main()
