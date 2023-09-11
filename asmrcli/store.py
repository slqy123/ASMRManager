# import click

# from logger import logger


# @click.command()
# def store():
#     import shutil
#     import cutie

#     """
#     Store voices from download path to storage path, use fastcopy if available.
#     """

#     fastcopy_path = shutil.which('fcp')

#     if fastcopy_path is None:
#         logger.warning('fastcopy not found, using shutil.copytree instead.')
#         res = cutie.prompt_yes_or_no('Continue?')
#         if not res:
#             return
