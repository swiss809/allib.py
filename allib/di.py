import functools
import inspect
import typing


def provider(func=None, *, singleton=False):
	"""
	Decorator to mark a function as a provider.

	Args:
		singleton (bool): The returned value should be a singleton or shared
			instance. If False (the default) the provider function will be
			invoked again for every time it's needed for injection.

	Example:
		@provider
		def myfunc() -> MyClass:
			return MyClass(args)
	"""
	def _add_provider_annotations(wrapper, func):
		wrapper.__di__ = getattr(func, '__di__', {})
		hints = typing.get_type_hints(func)
		wrapper.__di__['provides'] = hints['return']
		wrapper.__di__['singleton'] = singleton

	if func is None:
		def decorator(func):
			@functools.wraps(func)
			def wrapper(*args, **kwargs):
				return func(*args, **kwargs)
			_add_provider_annotations(wrapper, func)
			return wrapper
		return decorator

	@functools.wraps(func)
	def wrapper(*args, **kwargs):
		return func(*args, **kwargs)
	_add_provider_annotations(wrapper, func)
	return wrapper


def inject(*args, **kwargs):
	"""
	Mark a class or function for injection, meaning that a DI container knows
	that it should inject dependencies into it.

	Normally you won't need this as the injector will inject the required
	arguments anyway, but it can be used to inject properties into a class
	without having to specify it in the constructor, or to inject arguments
	that aren't properly type hinted.

	Example:
		@di.inject('foo', MyClass)
		class MyOtherClass: pass
		assert isinstance(injector.get(MyOtherClass).foo, MyClass)
	"""
	def wrapper(obj):
		if inspect.isclass(obj) or callable(obj):
			inject_object(obj, *args, **kwargs)
			return obj
		raise Exception("Don't know how to inject into %r" % obj)
	return wrapper


def inject_object(obj, var_name, var_type):
	obj.__di__ = getattr(obj, '__di__', {})
	obj.__di__.setdefault('inject', {})[var_name] = var_type
	return obj


class Module:
	"""
	A module is a collection of providers.
	"""
	pass


class Injector:
	"""
	Class that knows how to do dependency injection.
	"""
	def __init__(self):
		self.instances = {}
		self.factories = {}

	def register_module(self, module: Module):
		"""
		Register a module.
		"""
		if inspect.isclass(module):
			module = self.get(module)
		if isinstance(module, Module):
			funcs = (
				item[1] for item in
				inspect.getmembers(module, predicate=inspect.ismethod)
			)
		else:
			raise Exception("Don't know how to register module: %r" % module)
		for func in funcs:
			if hasattr(func, '__di__') and func.__di__.get('provides'):
				self.register_provider(func)

	def register_provider(self, func):
		"""
		Register a provider function.
		"""
		if 'provides' not in getattr(func, '__di__', {}):
			raise Exception('Function %r is not a provider' % func)
		self.factories[func.__di__['provides']] = func

	def get(self, thing: type):
		"""
		Get an instance of some type.
		"""
		if thing in self.instances:
			return self.instances[thing]

		if thing in self.factories:
			fact = self.factories[thing]
			ret = self.get(fact)
			if hasattr(fact, '__di__') and fact.__di__['singleton']:
				self.instances[thing] = ret
			return ret

		if inspect.isclass(thing):
			return self._call_class_init(thing)
		elif callable(thing):
			return thing(**self._guess_kwargs(thing))

		raise Exception('not sure what thing is: %r' % thing)

	def _call_class_init(self, cls):
		# if this statement is true, the class or its parent class(es) does not
		# have an __init__ method defined and as such should not need any
		# constructor arguments to be instantiated.
		if cls.__init__ is object.__init__:
			obj = cls()
		else:
			obj = cls(**self._guess_kwargs(cls.__init__))

		# extra properties defined with @di.inject
		if hasattr(obj, '__di__') and 'inject' in obj.__di__:
			for prop_name, prop_type in obj.__di__['inject'].items():
				setattr(obj, prop_name, self.get(prop_type))

		return obj

	def _guess_kwargs(self, func):
		kwargs = {}
		hints = typing.get_type_hints(func)
		for arg in hints:
			if arg == 'return':
				continue
			kwargs[arg] = self.get(hints[arg])
		return kwargs