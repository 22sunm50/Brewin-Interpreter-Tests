# document that we won't have a return inside the init/update of a for loop

import copy
from enum import Enum

from brewparse import parse_program
from env_v2 import EnvironmentManager
from intbase import InterpreterBase, ErrorType
from type_valuev2 import Type, Value, create_value, get_printable, Thunk, UserException


class ExecStatus(Enum):
    CONTINUE = 1
    RETURN = 2


# Main interpreter class
class Interpreter(InterpreterBase):
    # constants
    NIL_VALUE = create_value(InterpreterBase.NIL_DEF)
    TRUE_VALUE = create_value(InterpreterBase.TRUE_DEF)
    BIN_OPS = {"+", "-", "*", "/", "==", "!=", ">", ">=", "<", "<=", "||", "&&"}

    # methods
    def __init__(self, console_output=True, inp=None, trace_output=False):
        super().__init__(console_output, inp)
        self.trace_output = trace_output
        self.__setup_ops()

    def run(self, program):
        try:
            ast = parse_program(program)
            self.__set_up_function_table(ast)
            self.env = EnvironmentManager()
            self.__call_func_aux("main", [])
        except UserException as e:
            self.error(ErrorType.FAULT_ERROR, f"Unhandled user-defined exception: {str(e)}")
        except Exception as e:
            raise # re-raise the exception for regular errors

    def __set_up_function_table(self, ast):
        self.func_name_to_ast = {}
        for func_def in ast.get("functions"):
            func_name = func_def.get("name")
            num_params = len(func_def.get("args"))
            if func_name not in self.func_name_to_ast:
                self.func_name_to_ast[func_name] = {}
            self.func_name_to_ast[func_name][num_params] = func_def

    def __get_func_by_name(self, name, num_params):
        if name not in self.func_name_to_ast:
            super().error(ErrorType.NAME_ERROR, f"Function {name} not found")
        candidate_funcs = self.func_name_to_ast[name]
        if num_params not in candidate_funcs:
            super().error(
                ErrorType.NAME_ERROR,
                f"Function {name} taking {num_params} params not found",
            )
        return candidate_funcs[num_params]

    def __run_statements(self, statements): # return (status, return_val) of a func
        self.env.push_block()
        for statement in statements:
            if self.trace_output:
                print(statement)
            status, return_val = self.__run_statement(statement)
            if status == ExecStatus.RETURN:
                self.env.pop_block()
                return (status, return_val)
        self.env.pop_block()
        return (ExecStatus.CONTINUE, Interpreter.NIL_VALUE)

    def __run_statement(self, statement): # return (status, return_val) of a func
        status = ExecStatus.CONTINUE
        return_val = None
        if statement.elem_type == InterpreterBase.FCALL_NODE:
            self.__call_func(statement)
        elif statement.elem_type == "=":
            self.__assign(statement)
        elif statement.elem_type == InterpreterBase.VAR_DEF_NODE:
            self.__var_def(statement)
        elif statement.elem_type == InterpreterBase.RETURN_NODE:
            status, return_val = self.__do_return(statement)
        elif statement.elem_type == Interpreter.IF_NODE:
            status, return_val = self.__do_if(statement)
        elif statement.elem_type == Interpreter.FOR_NODE:
            status, return_val = self.__do_for(statement)
        elif statement.elem_type == InterpreterBase.RAISE_NODE:
            self.__handle_raise(statement)
        elif statement.elem_type == InterpreterBase.TRY_NODE:
            return self.__handle_try(statement)
        return (status, return_val)
    
    def __call_func(self, call_node): # return return_val
        func_name = call_node.get("name")
        actual_args = call_node.get("args")
        # print(f"⛄️: call func: {func_name}")
        # print(f"⛄️: self.env = {self.env.environment}")
        return self.__call_func_aux(func_name, actual_args)

    def __call_func_aux(self, func_name, actual_args): # return return_val
        if func_name == "print":
            return self.__call_print(actual_args)
        if func_name == "inputi" or func_name == "inputs":
            return self.__call_input(func_name, actual_args)

        func_ast = self.__get_func_by_name(func_name, len(actual_args))
        formal_args = func_ast.get("args")
        if len(actual_args) != len(formal_args):
            super().error(
                ErrorType.NAME_ERROR,
                f"Function {func_ast.get('name')} with {len(actual_args)} args not found",
            )

        # first evaluate all of the actual parameters and associate them with the formal parameter names
        args = {}
        curr_dict = copy.copy(self.env) # create a shallow copy of the curr env dict
        curr_dict.environment = [ # create a new environment structure where each list and dictionary is shallow-copied
            [copy.copy(env) for env in func_env] for func_env in self.env.environment
        ]
        for formal_ast, actual_ast in zip(formal_args, actual_args):
            # print(f"📱: self.env = {self.env.environment}")
            thunk = Thunk(actual_ast, curr_dict)
            # result = copy.copy(self.__eval_expr(actual_ast))
            arg_name = formal_ast.get("name")
            args[arg_name] = thunk

        # then create the new activation record 
        self.env.push_func()
        # and add the formal arguments to the activation record
        for arg_name, value in args.items():
            # print(f"📱: arg_name = {arg_name}")
            # print(f"📱: value env = {value.copied_env.environment}")
            self.env.create(arg_name, value)
        _, return_val = self.__run_statements(func_ast.get("statements"))
        self.env.pop_func()
        return return_val

    def __call_print(self, args): # return nil
        output = ""
        for arg in args:
            # eager eval
            # print(f"🖨️: arg = {arg}")
            # print(f"🖨️: self.env.get(arg) = {self.env.get('b').expr_ast}")
            result = self.__eval_expr(arg)  # result could be Thunk or Value object
            output = output + get_printable(result)
        super().output(output)
        return Interpreter.NIL_VALUE

    def __call_input(self, name, args): # return Value object
        if args is not None and len(args) == 1:
            result = self.__eval_expr(args[0])
            super().output(get_printable(result))
        elif args is not None and len(args) > 1:
            super().error(
                ErrorType.NAME_ERROR, "No inputi() function that takes > 1 parameter"
            )
        inp = super().get_input()
        if name == "inputi":
            return Value(Type.INT, int(inp))
        if name == "inputs":
            return Value(Type.STRING, inp)

    def __assign(self, assign_ast): # no return
        var_name = assign_ast.get("name")
        expr_ast = assign_ast.get("expression")

        curr_dict = copy.copy(self.env) # create a shallow copy of the curr env dict
        curr_dict.environment = [ # create a new environment structure where each list and dictionary is shallow-copied
            [copy.copy(env) for env in func_env] for func_env in self.env.environment
        ]
        # create thunk
        thunk_obj = Thunk(expr_ast, curr_dict)
        # set thunk to dict
        if not self.env.set(var_name, thunk_obj):
            super().error(
                ErrorType.NAME_ERROR, f"Undefined variable {var_name} in assignment"
            )
    
    def __var_def(self, var_ast): # no return
        var_name = var_ast.get("name")
        if not self.env.create(var_name, Interpreter.NIL_VALUE):
            super().error(
                ErrorType.NAME_ERROR, f"Duplicate definition for variable {var_name}"
            )

    def __eval_expr(self, expr_ast): # return Value Object
        if expr_ast.elem_type == InterpreterBase.NIL_NODE:
            return Interpreter.NIL_VALUE
        if expr_ast.elem_type == InterpreterBase.INT_NODE:
            return Value(Type.INT, expr_ast.get("val"))
        if expr_ast.elem_type == InterpreterBase.STRING_NODE:
            return Value(Type.STRING, expr_ast.get("val"))
        if expr_ast.elem_type == InterpreterBase.BOOL_NODE:
            return Value(Type.BOOL, expr_ast.get("val"))
        if expr_ast.elem_type == InterpreterBase.VAR_NODE:
            var_name = expr_ast.get("name")
            val_thunk = self.env.get(var_name)
            if val_thunk is None:
                super().error(ErrorType.NAME_ERROR, f"Variable {var_name} not found")
            if not isinstance(val_thunk, Thunk): # then should be a Value obj?
                return val_thunk    
            val_thunk = self.__handle_thunk(val_thunk) # return Value Obj?
            return val_thunk
        if expr_ast.elem_type == InterpreterBase.FCALL_NODE:
            return self.__call_func(expr_ast)
        if expr_ast.elem_type in Interpreter.BIN_OPS:
            return self.__eval_op(expr_ast)
        if expr_ast.elem_type == Interpreter.NEG_NODE:
            return self.__eval_unary(expr_ast, Type.INT, lambda x: -1 * x)
        if expr_ast.elem_type == Interpreter.NOT_NODE:
            return self.__eval_unary(expr_ast, Type.BOOL, lambda x: not x)

    def __eval_op(self, arith_ast): # return Value Object
        op = arith_ast.elem_type
        # short circuiting
        if op  == '&&':
            left_value_obj = self.__eval_expr(arith_ast.get("op1"))
            if not left_value_obj.value():
                return Value(Type.BOOL, False)
            return self.__eval_expr(arith_ast.get("op2"))
        elif op == '||':
            left_value_obj = self.__eval_expr(arith_ast.get("op1"))
            if left_value_obj.value():
                return Value(Type.BOOL, True)
            return self.__eval_expr(arith_ast.get("op2"))

        left_value_obj = self.__eval_expr(arith_ast.get("op1"))
        right_value_obj = self.__eval_expr(arith_ast.get("op2"))

        # division by zero check (after evaluating both sides)
        if op == '/' and right_value_obj.value() == 0:
            raise UserException("div0")  # Custom exception for division by zero

        if not self.__compatible_types(
            arith_ast.elem_type, left_value_obj, right_value_obj
        ):
            super().error(
                ErrorType.TYPE_ERROR,
                f"Incompatible types for {arith_ast.elem_type} operation",
            )
        if arith_ast.elem_type not in self.op_to_lambda[left_value_obj.type()]:
            super().error(
                ErrorType.TYPE_ERROR,
                f"Incompatible operator {arith_ast.elem_type} for type {left_value_obj.type()}",
            )
        f = self.op_to_lambda[left_value_obj.type()][arith_ast.elem_type]
        return f(left_value_obj, right_value_obj)

    def __compatible_types(self, oper, obj1, obj2): # return Bool
        # DOCUMENT: allow comparisons ==/!= of anything against anything
        if oper in ["==", "!="]:
            return True
        return obj1.type() == obj2.type()

    def __eval_unary(self, arith_ast, t, f): # return Value Object
        value_obj = self.__eval_expr(arith_ast.get("op1"))
        if value_obj.type() != t:
            super().error(
                ErrorType.TYPE_ERROR,
                f"Incompatible type for {arith_ast.elem_type} operation",
            )
        return Value(t, f(value_obj.value()))

    def __setup_ops(self): # no return
        self.op_to_lambda = {}
        # set up operations on integers
        self.op_to_lambda[Type.INT] = {}
        self.op_to_lambda[Type.INT]["+"] = lambda x, y: Value(
            x.type(), x.value() + y.value()
        )
        self.op_to_lambda[Type.INT]["-"] = lambda x, y: Value(
            x.type(), x.value() - y.value()
        )
        self.op_to_lambda[Type.INT]["*"] = lambda x, y: Value(
            x.type(), x.value() * y.value()
        )
        self.op_to_lambda[Type.INT]["/"] = lambda x, y: Value(
            x.type(), x.value() // y.value()
        )
        self.op_to_lambda[Type.INT]["=="] = lambda x, y: Value(
            Type.BOOL, x.type() == y.type() and x.value() == y.value()
        )
        self.op_to_lambda[Type.INT]["!="] = lambda x, y: Value(
            Type.BOOL, x.type() != y.type() or x.value() != y.value()
        )
        self.op_to_lambda[Type.INT]["<"] = lambda x, y: Value(
            Type.BOOL, x.value() < y.value()
        )
        self.op_to_lambda[Type.INT]["<="] = lambda x, y: Value(
            Type.BOOL, x.value() <= y.value()
        )
        self.op_to_lambda[Type.INT][">"] = lambda x, y: Value(
            Type.BOOL, x.value() > y.value()
        )
        self.op_to_lambda[Type.INT][">="] = lambda x, y: Value(
            Type.BOOL, x.value() >= y.value()
        )
        #  set up operations on strings
        self.op_to_lambda[Type.STRING] = {}
        self.op_to_lambda[Type.STRING]["+"] = lambda x, y: Value(
            x.type(), x.value() + y.value()
        )
        self.op_to_lambda[Type.STRING]["=="] = lambda x, y: Value(
            Type.BOOL, x.value() == y.value()
        )
        self.op_to_lambda[Type.STRING]["!="] = lambda x, y: Value(
            Type.BOOL, x.value() != y.value()
        )
        #  set up operations on bools
        self.op_to_lambda[Type.BOOL] = {}
        self.op_to_lambda[Type.BOOL]["&&"] = lambda x, y: Value(
            x.type(), x.value() and y.value()
        )
        self.op_to_lambda[Type.BOOL]["||"] = lambda x, y: Value(
            x.type(), x.value() or y.value()
        )
        self.op_to_lambda[Type.BOOL]["=="] = lambda x, y: Value(
            Type.BOOL, x.type() == y.type() and x.value() == y.value()
        )
        self.op_to_lambda[Type.BOOL]["!="] = lambda x, y: Value(
            Type.BOOL, x.type() != y.type() or x.value() != y.value()
        )

        #  set up operations on nil
        self.op_to_lambda[Type.NIL] = {}
        self.op_to_lambda[Type.NIL]["=="] = lambda x, y: Value(
            Type.BOOL, x.type() == y.type() and x.value() == y.value()
        )
        self.op_to_lambda[Type.NIL]["!="] = lambda x, y: Value(
            Type.BOOL, x.type() != y.type() or x.value() != y.value()
        )

    def __do_if(self, if_ast): # return (status, return_val)
        cond_ast = if_ast.get("condition")
        result = self.__eval_expr(cond_ast)
        if result.type() != Type.BOOL:
            super().error(
                ErrorType.TYPE_ERROR,
                "Incompatible type for if condition",
            )
        if result.value():
            statements = if_ast.get("statements")
            status, return_val = self.__run_statements(statements)
            return (status, return_val)
        else:
            else_statements = if_ast.get("else_statements")
            if else_statements is not None:
                status, return_val = self.__run_statements(else_statements)
                return (status, return_val)

        return (ExecStatus.CONTINUE, Interpreter.NIL_VALUE)

    def __do_for(self, for_ast):
        init_ast = for_ast.get("init") 
        cond_ast = for_ast.get("condition")
        update_ast = for_ast.get("update") 

        self.__run_statement(init_ast)  # initialize counter variable
        # run_for = Interpreter.TRUE_VALUE
        # while run_for.value():
        #     run_for = self.__eval_expr(cond_ast)  # check for-loop condition
        #     if run_for.type() != Type.BOOL:
        #         super().error(
        #             ErrorType.TYPE_ERROR,
        #             "Incompatible type for for condition",
        #         )
        #     if run_for.value():
        #         statements = for_ast.get("statements")
        #         status, return_val = self.__run_statements(statements)
        #         if status == ExecStatus.RETURN:
        #             return status, return_val
        #         self.__run_statement(update_ast)  # update counter variable

        while self.__eval_expr(cond_ast).value():
            self.env.push_block()  # Create a new scope for each iteration
            try:
                status, return_val = self.__run_statements(for_ast.get("statements"))
                if status == ExecStatus.RETURN:
                    return status, return_val
            finally:
                self.env.pop_block()  # Ensure the block is always popped
            self.__run_statement(update_ast)  # Update counter variable

        return (ExecStatus.CONTINUE, Interpreter.NIL_VALUE)

    def __do_return(self, return_ast):
        expr_ast = return_ast.get("expression")
        if expr_ast is None:
            return (ExecStatus.RETURN, Interpreter.NIL_VALUE)
        
        value_obj = copy.copy(self.__eval_expr(expr_ast))
        return (ExecStatus.RETURN, value_obj)
    
    def __handle_thunk(self, thunk_obj): # return a Value Object        
        if not thunk_obj.is_evaluated:
            # print(f"👋: thunk_obj.copied_env = {thunk_obj.copied_env.environment}")
            thunk_obj.expr_ast = self.__eval_expr_thunk(thunk_obj.expr_ast, thunk_obj.copied_env)
            thunk_obj.is_evaluated = True

            # # update the environment with the resolved value
            # variable_name = thunk_obj.copied_env.get_variable_name_from_thunk(thunk_obj)
            # if variable_name:
            #     self.env.set(variable_name, thunk_obj.expr_ast)  # Update with resolved value

        return thunk_obj.expr_ast
    
    def __eval_expr_thunk(self, expr_ast, thunk_env):
        if expr_ast.elem_type == InterpreterBase.NIL_NODE:
            return Interpreter.NIL_VALUE
        if expr_ast.elem_type == InterpreterBase.INT_NODE:
            return Value(Type.INT, expr_ast.get("val"))
        if expr_ast.elem_type == InterpreterBase.STRING_NODE:
            return Value(Type.STRING, expr_ast.get("val"))
        if expr_ast.elem_type == InterpreterBase.BOOL_NODE:
            return Value(Type.BOOL, expr_ast.get("val"))
        if expr_ast.elem_type == InterpreterBase.VAR_NODE:
            var_name = expr_ast.get("name") # gets var from the Thunk's expr_ast
            val_thunk = thunk_env.get(var_name) # gets Thunk of var
            # print(f"🧮: val_thunk = {val_thunk}")
            if val_thunk is None: # had not been initiated prior to thunk creation
                super().error(ErrorType.NAME_ERROR, f"Variable {var_name} not found")
            # val_thunk = val_thunk.copied_env.get(var_name) # get the var stored in copied env
            
            if isinstance(val_thunk, Thunk): # if var in copied_env is another Thunk
                val_thunk = self.__handle_thunk(val_thunk)
            return val_thunk
        if expr_ast.elem_type == InterpreterBase.FCALL_NODE:
            # return self.__call_func(expr_ast)
            return self.__call_func_thunk(expr_ast, thunk_env)
        if expr_ast.elem_type in Interpreter.BIN_OPS:
            return self.__eval_op_thunk(expr_ast, thunk_env) # 🍅
        if expr_ast.elem_type == Interpreter.NEG_NODE:
            return self.__eval_unary(expr_ast, Type.INT, lambda x: -1 * x)
        if expr_ast.elem_type == Interpreter.NOT_NODE:
            return self.__eval_unary(expr_ast, Type.BOOL, lambda x: not x)
        
    def __eval_op_thunk(self, expr_ast, thunk_env): # return Value Object
        op = expr_ast.elem_type
        op1 = expr_ast.get("op1")
        op2 = expr_ast.get("op2")
        # short circuiting
        if op  == '&&':
            left_value_obj = self.__eval_expr_thunk(op1, thunk_env)
            if not left_value_obj.value():
                return Value(Type.BOOL, False)
            return self.__eval_expr_thunk(op2, thunk_env)
        elif op == '||':
            left_value_obj = self.__eval_expr_thunk(op1, thunk_env)
            if left_value_obj.value():
                return Value(Type.BOOL, True)
            return self.__eval_expr_thunk(op2, thunk_env)

        left_value_obj = self.__eval_expr_thunk(op1, thunk_env)
        right_value_obj = self.__eval_expr_thunk(op2, thunk_env)
        if not self.__compatible_types(
            expr_ast.elem_type, left_value_obj, right_value_obj
        ):
            super().error(
                ErrorType.TYPE_ERROR,
                f"Incompatible types for {expr_ast.elem_type} operation",
            )
        if expr_ast.elem_type not in self.op_to_lambda[left_value_obj.type()]:
            super().error(
                ErrorType.TYPE_ERROR,
                f"Incompatible operator {expr_ast.elem_type} for type {left_value_obj.type()}",
            )
        f = self.op_to_lambda[left_value_obj.type()][expr_ast.elem_type]
        return f(left_value_obj, right_value_obj)
    
    def __call_func_thunk(self, call_node, thunk_env): # return return_val
        func_name = call_node.get("name")
        actual_args = call_node.get("args")

        if func_name == "print":
            return self.__call_print(actual_args)
        if func_name == "inputi" or func_name == "inputs":
            return self.__call_input(func_name, actual_args)

        func_ast = self.__get_func_by_name(func_name, len(actual_args))
        formal_args = func_ast.get("args")
        if len(actual_args) != len(formal_args):
            super().error(
                ErrorType.NAME_ERROR,
                f"Function {func_ast.get('name')} with {len(actual_args)} args not found",
            )

        # Evaluate actual parameters using the thunk_env
        args = {}
        for formal_ast, actual_ast in zip(formal_args, actual_args):
            thunk = Thunk(actual_ast, copy.copy(thunk_env)) # 🍅 think about later: do I need to copy further? 
            # result = self.__eval_expr_thunk(actual_ast, thunk_env)  # Evaluate lazily
            arg_name = formal_ast.get("name")
            args[arg_name] = thunk

        # Push a new function environment
        self.env.push_func()
        for arg_name, value in args.items():
            self.env.create(arg_name, value)

        _, return_val = self.__run_statements(func_ast.get("statements"))
        self.env.pop_func()

        return return_val

    def __handle_raise(self, raise_ast):
        exception_expr = raise_ast.get("exception_type")
        exception_value = self.__eval_expr(exception_expr)
        if exception_value.type() != Type.STRING:
            super().error(ErrorType.TYPE_ERROR, f"Raised exception type is not a string, it is of type: {exception_value.type()}")
        raise UserException(exception_value.value()) # 🍅
    
    def __handle_try(self, try_ast):
        did_it_pop = False
        try_statements = try_ast.get("statements")
        catchers = try_ast.get("catchers")
        try:
            self.env.push_block()
            # self.__run_statements(try_statements)
            status, return_val = self.__run_statements(try_statements)
            self.env.pop_block()
            did_it_pop = True
            return status, return_val # ensure tuple is returned
        except UserException as e:
            if not did_it_pop:
                self.env.pop_block()
            self.env.push_block()
            exception_type = str(e)
            for catcher in catchers:
                if catcher.get("exception_type") == exception_type: # check if exceptions match
                    self.env.push_block() # new scope for catch clause
                    try:
                        # self.__run_statements(catcher.get("statements"))
                        status, return_val = self.__run_statements(catcher.get("statements"))
                        return status, return_val
                    finally:
                        self.env.pop_block()
            raise e # 🍅 if no matching catch block is found, re-raise the exception

def main():
  program = """
func foo(a) {
  print("a: ", a);
  return a + 1;
}

func bar(b) {
  print(b);
}

func main() {
  var x;
  x = foo(5);
  bar(x);
}

/*
*OUT*
a: 5
6
*OUT*
*/
                """
  interpreter = Interpreter()
  interpreter.run(program)


if __name__ == "__main__":
    main()