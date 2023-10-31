# playlist manager
import click


@click.group()
def pl():
    """asmr playlist interface"""


@click.command("list")
def list_():
    """list all playlists"""
    raise NotImplementedError


@click.command()
def add():
    """add a playlist"""
    raise NotImplementedError


@click.command("rm")
def remove():
    """remove a playlist"""
    raise NotImplementedError
