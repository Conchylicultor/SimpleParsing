""" Utility functions that simplify defining field of dataclasses.
"""
from __future__ import annotations

import dataclasses
import functools
import inspect
import warnings
from collections import OrderedDict
from dataclasses import _MISSING_TYPE, MISSING
from enum import Enum
from logging import getLogger
from typing import Any, Callable, Hashable, Iterable, TypeVar, overload

from simple_parsing.utils import Dataclass, DataclassT, str2bool

logger = getLogger(__name__)

E = TypeVar("E", bound=Enum)
K = TypeVar("K", bound=Hashable)
V = TypeVar("V")
T = TypeVar("T")


def field(
    default: T | _MISSING_TYPE = MISSING,
    alias: str | list[str] | None = None,
    cmd: bool = True,
    positional: bool = False,
    *,
    to_dict: bool = True,
    encoding_fn: Callable[[T], Any] | None = None,
    decoding_fn: Callable[[Any], T] | None = None,
    # dataclasses.field arguments
    default_factory: Callable[[], T] | _MISSING_TYPE = MISSING,
    init: bool = True,
    repr: bool = True,
    hash: bool | None = None,
    compare: bool = True,
    metadata: dict[str, Any] | None = None,
    **custom_argparse_args: Any,
) -> T:
    """Extension of the `dataclasses.field` function.

    Adds the ability to customize how this field's command-line options are
    created, as well as how it is serialized / deseralized (if the containing
    dataclass inherits from `simple_parsing.Serializable`.

    Leftover arguments are fed directly to the
    `ArgumentParser.add_argument(*option_strings, **kwargs)` method.

    Parameters
    ----------
    default : Union[T, _MISSING_TYPE], optional
        The default field value (same as in `dataclasses.field`), by default MISSING
    alias : Union[str, List[str]], optional
        Additional option_strings to pass to the `add_argument` method, by
        default None. When passing strings which do not start by "-" or "--",
        will be prefixed with "-" if the string is one character and by "--"
        otherwise.
    cmd: bool, optional
        Whether to add command-line arguments for this field or not. Defaults to
        True.

    ## Serialization-related Keyword Arguments:

    to_dict : bool
        Whether to include this field in the dictionary when calling `to_dict()`.
        Defaults to True.
        Only has an effect when the dataclass containing this field is
        `Serializable`.
    encoding_fn : Callable[[T], Any], optional
        Function to apply to this field's value when encoding the dataclass to a
        dict. Only has an effect when the dataclass containing this field is
        `Serializable`.
    decoding_fn : Callable[[Any], T]. optional
        Function to use in order to recover a the value of this field from a
        serialized entry in a dictionary (inside `cls.from_dict`).
        Only has an effect when the dataclass containing this field is
        `Serializable`.

    ## Keyword Arguments of `dataclasses.field`

    default_factory : Union[Callable[[], T], _MISSING_TYPE], optional
        (same as in `dataclasses.field`), by default None
    init : bool, optional
        (same as in `dataclasses.field`), by default True
    repr : bool, optional
        (same as in `dataclasses.field`), by default True
    hash : bool, optional
        (same as in `dataclasses.field`), by default None
    compare : bool, optional
        (same as in `dataclasses.field`), by default True
    metadata : Dict[str, Any], optional
        (same as in `dataclasses.field`), by default None

    Returns
    -------
    T
        The value returned by the `dataclasses.field` function.
    """
    _metadata: dict[str, Any] = metadata if metadata is not None else {}
    if alias:
        _metadata["alias"] = alias if isinstance(alias, list) else [alias]
    _metadata.update(dict(to_dict=to_dict))
    if encoding_fn is not None:
        _metadata.update(dict(encoding_fn=encoding_fn))
    if decoding_fn is not None:
        _metadata.update(dict(decoding_fn=decoding_fn))
    _metadata["cmd"] = cmd
    _metadata["positional"] = positional

    if custom_argparse_args:
        _metadata.update({"custom_args": custom_argparse_args})

        action = custom_argparse_args.get("action")
        if action == "store_false":
            if default not in {MISSING, True}:
                raise RuntimeError(
                    "default should either not be passed or set "
                    "to True when using the store_false action."
                )
            default = True  # type: ignore

        elif action == "store_true":
            if default not in {MISSING, False}:
                raise RuntimeError(
                    "default should either not be passed or set "
                    "to False when using the store_true action."
                )
            default = False  # type: ignore

    if default is not MISSING:
        return dataclasses.field(  # type: ignore
            default=default,
            init=init,
            repr=repr,
            hash=hash,
            compare=compare,
            metadata=_metadata,
        )
    elif not isinstance(default_factory, dataclasses._MISSING_TYPE):
        return dataclasses.field(
            default_factory=default_factory,
            init=init,
            repr=repr,
            hash=hash,
            compare=compare,
            metadata=_metadata,
        )
    else:
        return dataclasses.field(
            init=init, repr=repr, hash=hash, compare=compare, metadata=_metadata
        )


@overload
def choice(choices: type[E], default: E, **kwargs) -> E:
    pass


@overload
def choice(choices: dict[K, V], default: K, **kwargs) -> V:
    pass


@overload
def choice(*choices: T, default: T, **kwargs) -> T:
    pass


# TODO: Fix the signature for this.
def choice(*choices: T, default: T | _MISSING_TYPE = MISSING, **kwargs: Any) -> T:
    """Makes a field which can be chosen from the set of choices from the
    command-line.

    Returns a regular `dataclasses.field()`, but with metadata which indicates
    the allowed values.

    (New:) If `choices` is a dictionary, then passing the 'key' will result in
    the corresponding value being used. The values may be objects, for example.
    Similarly for Enum types, passing a type of enum will

    Args:
        default (T, optional): The default value of the field. Defaults to dataclasses.MISSING,
        in which case the command-line argument is required.

    Raises:
        ValueError: If the default value isn't part of the given choices.

    Returns:
        T: the result of the usual `dataclasses.field()` function (a dataclass field/attribute).
    """
    assert len(choices) > 0, "Choice requires at least one positional argument!"

    if len(choices) == 1:
        choices = choices[0]
        if inspect.isclass(choices) and issubclass(choices, Enum):
            # If given an enum, construct a mapping from names to values.
            choice_enum: type[Enum] = choices
            choices = OrderedDict((e.name, e) for e in choice_enum)
            if default is not MISSING and not isinstance(default, choice_enum):
                if default in choices:
                    warnings.warn(
                        UserWarning(
                            f"Setting default={default} could perhaps be ambiguous "
                            f"(enum names vs enum values). Consider using the enum "
                            f"value {choices[default]} instead."
                        )
                    )
                    default = choices[default]
                else:
                    raise ValueError(
                        f"'default' arg should be of type {choice_enum}, but got {default}"
                    )

        if isinstance(choices, dict):
            # if the choices is a dict, the options are the keys
            # save the info about the choice_dict in the field metadata.
            metadata = kwargs.setdefault("metadata", {})
            choice_dict = choices
            # save the choice_dict in metadata so that we can recover the values in postprocessing.
            metadata["choice_dict"] = choice_dict
            choices = list(choice_dict.keys())

            # TODO: If the choice dict is given, then add encoding/decoding functions that just
            # get/set the right key.
            def _encoding_fn(value: Any) -> str:
                """Custom encoding function that will simply represent the value as the
                the key in the dict rather than the value itself.
                """
                if value in choice_dict.keys():
                    return value
                elif value in choice_dict.values():
                    return [k for k, v in choice_dict.items() if v == value][0]
                return value

            kwargs.setdefault("encoding_fn", _encoding_fn)

            def _decoding_fn(value: Any) -> str:
                """Custom decoding function that will retrieve the value from the
                stored key in the dictionary.
                """
                return choice_dict.get(value, value)

            kwargs.setdefault("decoding_fn", _decoding_fn)

    return field(default=default, choices=choices, **kwargs)


def list_field(*default_items: T, **kwargs) -> list[T]:
    """shorthand function for setting a `list` attribute on a dataclass,
    so that every instance of the dataclass doesn't share the same list.

    Accepts any of the arguments of the `dataclasses.field` function.

    Returns:
        List[T]: a `dataclasses.field` of type `list`, containing the `default_items`.
    """
    default = kwargs.pop("default", None)
    if isinstance(default, list):
        # can't have that. field wants a default_factory.
        # we just give back a copy of the list as a default factory,
        # but this should be discouraged.
        from copy import deepcopy

        kwargs["default_factory"] = lambda: deepcopy(default)
    return mutable_field(list, default_items, **kwargs)


def dict_field(default_items: dict[K, V] | Iterable[tuple[K, V]] = None, **kwargs) -> dict[K, V]:
    """shorthand function for setting a `dict` attribute on a dataclass,
    so that every instance of the dataclass doesn't share the same `dict`.

    NOTE: Do not use keyword arguments as you usually would with a dictionary
    (as in something like `dict_field(a=1, b=2, c=3)`). Instead pass in a
    dictionary instance with the items: `dict_field(dict(a=1, b=2, c=3))`.
    The reason for this is that the keyword arguments are interpreted as custom
    argparse arguments, rather than arguments of the `dict` function!)

    Also accepts any of the arguments of the `dataclasses.field` function.

    Returns:
        Dict[K, V]: a `dataclasses.Field` of type `Dict[K, V]`, containing the `default_items`.
    """
    if default_items is None:
        default_items = {}
    elif isinstance(default_items, dict):
        default_items = default_items.items()
    return mutable_field(dict, default_items, **kwargs)


def set_field(*default_items: T, **kwargs) -> set[T]:
    return mutable_field(set, default_items, **kwargs)


def mutable_field(
    _type: type[T],
    *args,
    init: bool = True,
    repr: bool = True,
    hash: bool = None,
    compare: bool = True,
    metadata: dict[str, Any] = None,
    **kwargs,
) -> T:
    # TODO: Check whether some of the keyword arguments are destined for the `field` function, or for the partial?
    default_factory = kwargs.pop("default_factory", functools.partial(_type, *args))
    return field(
        default_factory=default_factory,
        init=init,
        repr=repr,
        hash=hash,
        compare=compare,
        metadata=metadata,
        **kwargs,
    )


MutableField = mutable_field

# TODO: Change this to a bound of Hashable.
# It seems to consider `default`
Key = TypeVar("Key", str, int, bool, Enum)
OtherDataclassT = TypeVar("OtherDataclassT", bound=Dataclass)


@overload
def subgroups(
    subgroups: dict[Key, type[DataclassT]],
    *args,
    default: Key,
    default_factory: _MISSING_TYPE = MISSING,
    **kwargs,
) -> DataclassT:
    ...


# TODO: Enable this overload if we make `subgroups` more flexible (see below).
# @overload
# def subgroups(
#     subgroups: Mapping[Key, type[DataclassT]],
#     *args,
#     default_factory: Callable[[], OtherDataclassT],
#     **kwargs,
# ) -> DataclassT | OtherDataclassT:
#     ...


@overload
def subgroups(
    subgroups: dict[Key, type[DataclassT]],
    *args,
    default: _MISSING_TYPE = MISSING,
    default_factory: type[DataclassT],
    **kwargs,
) -> DataclassT:
    ...


@overload
def subgroups(
    subgroups: dict[Key, type[DataclassT]],
    *args,
    default: _MISSING_TYPE = MISSING,
    default_factory: _MISSING_TYPE = MISSING,
    **kwargs,
) -> DataclassT:
    ...


def subgroups(
    subgroups: dict[Key, type[DataclassT]],
    *args,
    default: Key | _MISSING_TYPE = MISSING,
    default_factory: type[DataclassT] | _MISSING_TYPE = MISSING,
    **kwargs,
) -> DataclassT:
    """Creates a field that will be a choice between different subgroups of arguments.

    This is different than adding a subparser action. There can only be one subparser action, while
    there can be arbitrarily many subgroups. Subgroups can also be nested!

    TODO: Support using functools.partial or maybe arbitrary callables (e.g. lambdas) in addition
    to dataclass types.

    Parameters
    ----------
    subgroups :
        Dictionary mapping from the subgroup name to the subgroup type.
    default :
        The default subgroup to use, by default MISSING, in which case a subgroup has to be
        selected. Needs to be a key in the subgroups dictionary.
    default_factory :
        The default_factory to use to create the subgroup. Needs to be a value of the `subgroups`
        dictionary.

    Returns
    -------
    A field whose type is the Union of the different possible subgroups.
    """
    if not all(
        inspect.isclass(subgroup) and dataclasses.is_dataclass(subgroup)
        for subgroup in subgroups.values()
    ):
        raise ValueError("All values in the subgroups dict need to be dataclasses!")
    metadata = kwargs.setdefault("metadata", {})
    metadata["subgroups"] = subgroups
    metadata["subgroup_default"] = default

    choices = subgroups.keys()
    kwargs["type"] = str

    if default_factory is not MISSING and default is not MISSING:
        raise ValueError("Can't pass both default and default_factory!")
    if default is not MISSING and default not in subgroups:
        raise ValueError("default must be a key in the subgroups dict!")
    if default_factory is not MISSING and default_factory not in subgroups.values():
        # TODO: This might a little bit too strict. We don't want to encourage people creating lots
        # of classes just to change the default arguments.
        raise ValueError("default_factory must be a value in the subgroups dict!")

    if default is not MISSING:
        assert default in subgroups.keys()
        default_factory = subgroups[default]
        metadata["subgroup_default"] = default
        default = MISSING

    elif default_factory is not MISSING:
        assert default_factory in subgroups.values()
        # default_factory passed, which is in the subgroups dict. Find the matching key.
        matching_keys = [k for k, v in subgroups.items() if v is default_factory]
        if not matching_keys:
            # Use == instead of `is` this time.
            matching_keys = [k for k, v in subgroups.items() if v == default_factory]

        # We wouldn't get here if default_factory wasn't in the subgroups dict values.
        assert matching_keys
        if len(matching_keys) > 1:
            raise ValueError(
                f"Default subgroup {default} is found more than once in the subgroups dict?"
            )
        subgroup_default = matching_keys[0]
        metadata["subgroup_default"] = subgroup_default
    else:
        # Store `MISSING` as the subgroup default.
        metadata["subgroup_default"] = MISSING

    return choice(choices, *args, default=default, default_factory=default_factory, **kwargs)  # type: ignore


def subparsers(
    subcommands: dict[str, type[Dataclass]], default: Dataclass = MISSING, **kwargs
) -> Any:
    return field(
        metadata={
            "subparsers": subcommands,
        },
        default=default,
        **kwargs,
    )


def flag(default: bool, **kwargs):
    """Creates a boolean field with a default value of `default` and nargs='?'."""
    action = "store_true" if default is False else "store_false"
    return field(default=default, nargs="?", action=action, type=str2bool, **kwargs)
