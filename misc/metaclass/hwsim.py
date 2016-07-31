from copy import deepcopy

from six import iteritems, with_metaclass


def deepish_copy(org):
    """
    https://writeonly.wordpress.com/2009/05/07/deepcopy-is-a-pig-for-simple-data/
    much, much faster than deepcopy, for a dict of the simple python types.
    """
    out = dict().fromkeys(org)
    # for k,v in org.iteritems():

    # for k,v in org.items():
    for k, v in iteritems(org):
        try:
            out[k] = v.copy()  # dicts, sets
        except AttributeError:
            try:
                out[k] = v[:]  # lists, tuples, strings, unicode
            except TypeError:
                out[k] = v  # ints

    return out


def clock_tick(func):
    """ Update register values from "next" """

    def clock_tick_wrap(*args, **kwargs):
        now = args[0].__dict__
        next = args[0].__dict__['next'].__dict__

        now.update(deepish_copy(next))

        ret = func(*args, **kwargs)
        return ret

    clock_tick_wrap.__wrapped__ = clock_tick
    return clock_tick_wrap


class Meta(type):
    """
    https://blog.ionelmc.ro/2015/02/09/understanding-python-metaclasses/#python-2-metaclass
    """

    def __new__(mcs, name, bases, attrs, **kwargs):
        # print('  Meta.__new__(mcs=%s, name=%r, bases=%s, attrs=[%s], **%s)' % (mcs, name, bases, ', '.join(attrs), kwargs))
        # attrs['__call__'] = clock_tick(attrs['__call__'])
        if '__call__' in attrs:
            # decorate the __call__ function with clock_tick
            attrs['__call__'] = clock_tick(attrs['__call__'])
        else:
            pass
        ret = super().__new__(mcs, name, bases, attrs)
        return ret

    # def __init__(cls, name, bases, attrs, **kwargs):
    #     if '__call__' in attrs:
    #         # decorate the __call__ function with clock_tick
    #         attrs['__call__'] = clock_tick(attrs['__call__'])
    #     else:
    #         pass
    #         # raise Exception('Class is missing __call__ function!')
    #     # print('  Meta.__init__(cls=%s, name=%r, bases=%s, attrs=[%s], **%s)' % (cls, name, bases, ', '.join(attrs), kwargs))
    #     ret = super().__init__(name, bases, attrs)
    #     return ret

    # ran when instance is made
    def __call__(cls, *args, **kwargs):
        # print('  Meta.__call__(cls=%s, args=%s, kwargs=%s)' % (cls, args, kwargs))
        ret = super().__call__(*args, **kwargs)
        ret.__dict__['next'] = deepcopy(ret)
        return ret


class HW(with_metaclass(Meta)):
    """ Only for metaclass inheritance """
    pass
